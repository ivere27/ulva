"""Meaningful order selection invariants, independent of KiCad or supplier access."""
import csv
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
from unittest import mock
import unittest
import xml.etree.ElementTree as ET

TOOL = Path(os.environ.get('ULVA_ORDER_TOOL', Path(__file__).resolve().parent / 'prepare_orders.py'))
spec = importlib.util.spec_from_file_location('orders', TOOL)
orders = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orders)
NOW = dt.datetime(2026, 10, 21, 12, tzinfo=dt.timezone.utc)


def fixture():
    root = ET.Element('export');components = ET.SubElement(root, 'components');positions = {}
    for ref, code, value, assembly in [('R1','C1','10k','JLC PCBA SMT'),('R2','C1','10k / 1%','JLC PCBA SMT'),('C1','C2','100nF','JLC PCBA SMT'),('U1','C3','REG','Manual SMT'),('J1','','HEADER','Manual THT'),('JP1','','JUMPER','PCB copper; no purchased part')]:
        c=ET.SubElement(components,'comp',ref=ref)
        ET.SubElement(c,'value').text=value;ET.SubElement(c,'footprint').text='Test:Part'
        fields=ET.SubElement(c,'fields')
        for name,text in {'MPN':'MPN-'+code if code else ref,'LCSC':code,'Assembly':assembly,'JLCPCB_Library':'Basic'}.items():
            ET.SubElement(fields,'field',name=name).text=text
        positions[ref]={'value':value,'footprint':'Part','smd':True,'dnp':False,'excluded':False,'position':{'Designator':ref,'Mid X':'1mm','Mid Y':'2mm','Layer':'Top','Rotation':'0'}}
    catalog={'schema_version':1,'parts':{c:{'tier':tier,'verified':True,'identity_verified':True,'mpn':'MPN-'+c,'source_url':'https://jlcpcb.com/partdetail/'+c,'checked_at':NOW.isoformat()} for c,tier in [('C1','basic'),('C2','unknown'),('C3','preferred')]}}
    receipt={'source_digest':'source','source_files_sha256':{'test':'hash'}}
    return root,positions,catalog,receipt


class OrderTests(unittest.TestCase):
    def model(self, mutate=None):
        inputs=fixture()
        if mutate:mutate(*inputs)
        return orders.make_model(*inputs,boards=5,max_age_days=30,now=NOW)

    def test_defaults_and_no_metadata_inference(self):
        m=self.model();choices=orders.selection_for(m)['choices']
        self.assertEqual(choices,{'C1':'loose','J1':'none','JP1':'none','R1':'pcba','R2':'pcba','U1':'loose'})
        self.assertEqual([r['ref'] for r in m['rows'] if r['manual']],['J1'])

    def test_quantity_consolidation_and_bom_cpl_exact_parity(self):
        m=self.model();s=orders.selection_for(m);s['boards']=7
        files=orders.output_files(m,s)
        bom=list(csv.DictReader(io.StringIO(files['jlc-bom.csv'])));cpl=list(csv.DictReader(io.StringIO(files['jlc-cpl.csv'])))
        self.assertEqual({r['Designator'] for r in bom},{r['Designator'] for r in cpl})
        self.assertEqual({r['Comment'] for r in bom},{'10k','10k / 1%'})
        s['choices']['R1']=s['choices']['R2']='loose'
        loose=list(csv.DictReader(io.StringIO(orders.output_files(m,s)['lcsc-import.csv'])))
        self.assertEqual(next(r for r in loose if r['LCSC Part Number']=='C1')['Quantity'],'14')
        self.assertEqual(orders.output_files(m,s)['jlc-cpl.csv'].count('\n'),1)

    def test_unknown_stale_future_or_nonofficial_catalog_fails_closed(self):
        variants=[{}, {'tier':'basic','verified':True,'identity_verified':True,'checked_at':'2020-01-01T00:00:00Z','source_url':'https://jlcpcb.com/x'},
                  {'tier':'basic','verified':True,'identity_verified':True,'checked_at':'2030-01-01T00:00:00Z','source_url':'https://jlcpcb.com/x'},
                  {'tier':'basic','verified':True,'identity_verified':True,'checked_at':NOW.isoformat(),'source_url':'https://jlcpcb.com.evil.test/x'}]
        for evidence in variants:self.assertEqual(orders.verified_tier(evidence,NOW,30),'unknown')
        m=self.model(lambda x,p,c,r:c['parts'].clear());self.assertFalse(any(r['pcba_allowed'] for r in m['rows']))

    def test_mpn_mismatch_blocked_dnp_and_features_cannot_order(self):
        m=self.model(lambda x,p,c,r:c['parts']['C1'].update(mpn='WRONG'))
        self.assertEqual(orders.selection_for(m)['choices']['R1'],'none')
        m=self.model(lambda x,p,c,r:p['R1'].update(dnp=True));s=orders.selection_for(m)
        for ref in ('R1','JP1'):
            bad=json.loads(json.dumps(s));bad['choices'][ref]='loose'
            with self.assertRaises(ValueError):orders.output_files(m,bad)

    def test_selection_scope_quantities_and_reference_set(self):
        m=self.model();s=orders.selection_for(m)
        for key,val in [('source_digest','stale'),('model_digest','stale'),('boards',0),('boards',2.5),('boards',True)]:
            bad=s|{key:val}
            with self.assertRaises(ValueError):orders.validate_selection(m,bad)
        for val in ['pcba,loose',['pcba','loose']]:
            bad=json.loads(json.dumps(s));bad['choices']['R1']=val
            with self.assertRaises((ValueError,TypeError)):orders.validate_selection(m,bad)
        bad=json.loads(json.dumps(s));del bad['choices']['R1']
        with self.assertRaises(ValueError):orders.validate_selection(m,bad)

    def test_refill_and_save_failures_stop_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'board.kicad_pcb'
            path.with_suffix('.kicad_pro').write_text('unchanged project')
            for fill_result,save_result,message in [(False,True,'zone refill failed'),(True,False,'snapshot save failed')]:
                with self.subTest(message=message):
                    board=types.SimpleNamespace(BuildConnectivity=mock.Mock(),Zones=mock.Mock(return_value=[]))
                    fill=mock.Mock(return_value=fill_result);save=mock.Mock(return_value=save_result)
                    module=types.SimpleNamespace(LoadBoard=mock.Mock(return_value=board),ZONE_FILLER=lambda b:types.SimpleNamespace(Fill=fill),SaveBoard=save)
                    with mock.patch.dict('sys.modules',{'pcbnew':module}):
                        with self.assertRaisesRegex(ValueError,message):orders.refill_pcb(path)
                    module.LoadBoard.assert_called_once()
                    if fill_result is False:save.assert_not_called()
                    self.assertEqual(path.with_suffix('.kicad_pro').read_text(),'unchanged project')

    def test_html_payload_is_safe_and_roundtrips_exact_text(self):
        data={'value':'</script><script>alert(1)</script>&'}
        payload=orders.html_payload(data)
        self.assertNotIn('</script>',payload)
        self.assertEqual(json.loads(payload),data)

    def test_custom_npth_mounting_slots_are_not_purchased(self):
        m=self.model(lambda x,p,c,r:p['J1'].update(mechanical=True))
        row=next(r for r in m['rows'] if r['ref']=='J1')
        self.assertTrue(row['no_part']);self.assertFalse(row['manual'])

    def test_spreadsheet_formula_cells_are_rejected(self):
        for text in ['=1+1', '+SUM(A1)', '-cmd|evil', '@SUM(A1)', '\t=1', '  =1']:
            with self.assertRaisesRegex(ValueError, 'spreadsheet formula'):
                orders.csv_text(['Value'], [[text]])
        self.assertIn('-1.0mm', orders.csv_text(['X'], [['-1.0mm']]))

    def test_stale_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)
            for ext in ('kicad_pcb','kicad_sch','kicad_pro'):(source/f'ulva_controller.{ext}').write_text(ext)
            receipt={'source_files_sha256':{name:orders.sha(data) for name,data in orders.source_files(source).items()}}
            orders.check_source(source,receipt)
            (source/'ulva_controller.kicad_pcb').write_text('changed')
            with self.assertRaisesRegex(ValueError,'source changed'):orders.check_source(source,receipt)

    def test_footprint_or_reference_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'value or footprint'):self.model(lambda x,p,c,r:p['R1'].update(value='wrong'))
        with self.assertRaisesRegex(ValueError,'reference sets'):self.model(lambda x,p,c,r:p.pop('R1'))


if __name__=='__main__':unittest.main()
