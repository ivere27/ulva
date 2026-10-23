#!/usr/bin/env python3
"""Prepare read-only KiCad snapshots with complete illustrative 3D assemblies.

Standard library models retain their upstream license. Original parametric
models are visual approximations, not dimensioned manufacturing drawings.
"""
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request

import pcbnew as p


COLORS = {
    'black': (0.055, 0.065, 0.075), 'plastic': (0.10, 0.115, 0.125),
    'silver': (0.68, 0.72, 0.74), 'gold': (0.78, 0.59, 0.20),
    'yellow': (0.94, 0.67, 0.04), 'ceramic': (0.83, 0.80, 0.70),
    'ferrite': (0.19, 0.20, 0.22), 'copper': (0.66, 0.37, 0.17),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_position(value):
    return (p.ToMM(value.x), p.ToMM(value.y))


def local_point(fp, point):
    x, y = native_position(point)
    ox, oy = native_position(fp.GetPosition())
    angle = math.radians(fp.GetOrientationDegrees())
    # Board coordinates use downward Y; model coordinates use upward Y.
    return (math.cos(angle)*(x-ox)-math.sin(angle)*(y-oy),
            -(math.sin(angle)*(x-ox)+math.cos(angle)*(y-oy)))


def pad_geometry(fp):
    return [{'number': pad.GetNumber(), 'xy': local_point(fp, pad.GetPosition()),
             'size': native_position(pad.GetSize()), 'drill': native_position(pad.GetDrillSize())}
            for pad in fp.Pads()]


def body_bounds(fp):
    points = []
    for item in fp.GraphicalItems():
        if isinstance(item, p.PCB_SHAPE) and item.GetLayer() == p.F_Fab:
            # Straight outlines and rectangle corners bound these custom bodies.
            points.extend([local_point(fp, item.GetStart()), local_point(fp, item.GetEnd())])
    if not points:
        points = [pad['xy'] for pad in pad_geometry(fp)]
        if len(points) == 1:
            x, y = points[0]
            return [x-1, y-1, x+1, y+1]
    return [min(x for x, y in points), min(y for x, y in points),
            max(x for x, y in points), max(y for x, y in points)]


class Mesh:
    def __init__(self):
        self.shapes = []

    def add(self, points, faces, material):
        color = ' '.join(str(v) for v in COLORS[material])
        metal = material in {'silver', 'gold', 'copper'}
        coords = ', '.join(' '.join(f'{v/2.54:.7f}' for v in pt) for pt in points)
        indices = ', '.join(' '.join(map(str, face))+' -1' for face in faces)
        self.shapes.append('Shape { appearance Appearance { material Material { '
            f'diffuseColor {color} specularColor {"0.65 0.65 0.65" if metal else "0.12 0.12 0.12"} '
            f'shininess {0.55 if metal else 0.18} }} }} geometry IndexedFaceSet {{ '
            f'solid FALSE creaseAngle 0.5 coord Coordinate {{ point [ {coords} ] }} '
            f'coordIndex [ {indices} ] }} }}')

    def box(self, xmin, ymin, zmin, xmax, ymax, zmax, material):
        if min(xmax-xmin, ymax-ymin, zmax-zmin) <= 0:
            return
        points = [(x,y,z) for z in (zmin,zmax) for y in (ymin,ymax) for x in (xmin,xmax)]
        self.add(points, [(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)], material)

    def tube(self, start, end, radius, material, sides=16):
        axis = [b-a for a,b in zip(start,end)]
        length = math.sqrt(sum(v*v for v in axis))
        if length < 1e-8:
            return
        axis = [v/length for v in axis]
        trial = [1,0,0] if abs(axis[0]) < .8 else [0,1,0]
        cross = lambda a,b: [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
        u = cross(axis,trial);norm = math.sqrt(sum(v*v for v in u));u=[v/norm for v in u];v=cross(axis,u)
        points=[]
        for center in (start,end):
            for i in range(sides):
                angle=2*math.pi*i/sides
                points.append(tuple(center[j]+radius*(math.cos(angle)*u[j]+math.sin(angle)*v[j]) for j in range(3)))
        faces=[tuple(reversed(range(sides))),tuple(range(sides,2*sides))]
        faces += [(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
        self.add(points,faces,material)

    def ring_box(self, bounds, z0, z1, wall, material):
        x0,y0,x1,y1=bounds
        self.box(x0,y0,z0,x1,y0+wall,z1,material)
        self.box(x0,y1-wall,z0,x1,y1,z1,material)
        self.box(x0,y0+wall,z0,x0+wall,y1-wall,z1,material)
        self.box(x1-wall,y0+wall,z0,x1,y1-wall,z1,material)

    def save(self,path,reference):
        path.write_text('#VRML V2.0 utf8\n# Original render-only approximation for '+reference+
            '\n# Coordinates are millimetres divided by 2.54; KiCad model scale is 1.\n'
            '# XY derives from footprint F.Fab/pads; heights and details are illustrative.\n'+
            '\n'.join(self.shapes)+'\n')


def make_model(fp, destination):
    ref=fp.GetReference();pads=pad_geometry(fp);bounds=body_bounds(fp)
    x0,y0,x1,y1=bounds;cx=(x0+x1)/2;cy=(y0+y1)/2
    mesh=Mesh();height=1.0;kind='generic'
    if ref in {'J1','J2','J3','J4','J6','J7'}:
        kind='open female socket';height=8.5
        # Individual cells leave real, open square receptacle mouths.
        for pad in pads:
            x,y=pad['xy'];w=(x1-x0)/2
            cell=[x-w,y-1.27,x+w,y+1.27]
            hole=.52
            mesh.box(cell[0],cell[1],.15,x-hole,cell[3],height,'black')
            mesh.box(x+hole,cell[1],.15,cell[2],cell[3],height,'black')
            mesh.box(x-hole,cell[1],.15,x+hole,y-hole,height,'black')
            mesh.box(x-hole,y+hole,.15,x+hole,cell[3],height,'black')
            mesh.box(x-.38,y-.38,.25,x+.38,y+.38,5.7,'gold')
            mesh.box(x-.25,y-.25,-2.5,x+.25,y+.25,.3,'gold')
    elif ref in {'J8','J9','J10','J11'}:
        kind='shrouded IDC header';height=9.1
        mesh.box(x0,y0,.15,x1,y1,1.65,'black')
        mesh.ring_box(bounds,1.6,height,.85,'black')
        # Polarizing key relief: the front lip is visibly lower at the center.
        for pad in pads:
            x,y=pad['xy'];mesh.box(x-.31,y-.31,-2.5,x+.31,y+.31,7.8,'gold')
    elif ref in {'J26','J27'}:
        kind='yellow AMASS power/data connector';height=9.0
        mesh.box(x0,y0,.3,x1,y1,height,'yellow')
        # Separate front contacts and their dark recessed surroundings.
        for pad in pads:
            x,y=pad['xy'];r=min(pad['drill'][0]*.38,.68)
            mesh.tube((x,y,-2.2),(x,y,2.6),r,'gold')
            mesh.tube((x,y,2.6),(x,min(y1,y+.8),2.6),r,'gold')
            if pad['number'] in {'1','2'}:
                mesh.tube((x,y0-.03,4.7),(x,y0+.08,4.7),1.65,'black',24)
                mesh.tube((x,y0-.07,4.7),(x,y0-.03,4.7),1.10,'gold',24)
            else:
                mesh.tube((x,y0-.04,2.2),(x,y0+.02,2.2),.65,'black')
                mesh.tube((x,y0-.08,2.2),(x,y0-.04,2.2),.35,'gold')
    elif ref=='K1':
        kind='slim rectangular relay';height=15.4
        mesh.box(x0,y0,.35,x1,y1,height,'black')
        mesh.box(x0+.25,y0+.25,.2,x1-.25,y1-.25,.4,'plastic')
        for pad in pads:
            x,y=pad['xy'];mesh.box(x-.25,y-.3,-3,x+.25,y+.3,.5,'silver')
    elif ref=='L1':
        kind='shielded power inductor';height=4.5
        mesh.box(x0,y0,.25,x1,y1,height,'ferrite')
        mesh.tube((cx,cy,height),(cx,cy,height+.025),min(x1-x0,y1-y0)*.37,'plastic',32)
        for pad in pads:
            x,y=pad['xy'];mesh.box(x-1.4,y-.9,.02,x+1.4,y+.9,.55,'silver')
    elif ref in {'SW2','SW3','SW4'}:
        kind='tactile switch';height=2.5
        mesh.box(x0,y0,.15,x1,y1,1.3,'black')
        mesh.box(x0+.08,y0+.08,1.3,x1-.08,y1-.08,1.65,'silver')
        mesh.tube((cx,cy,1.64),(cx,cy,height),1.3,'black',24)
        for pad in pads:
            x,y=pad['xy'];mesh.box(x-.55,y-.55,.05,x+.55,y+.55,.35,'silver')
    elif ref in {'F2','F3'}:
        kind='ceramic chip fuse';height=.65
        mesh.box(x0,y0,.05,x1,y1,height,'ceramic')
        mesh.box(x0-.03,y0-.02,.02,x0+.32,y1+.02,height+.03,'silver')
        mesh.box(x1-.32,y0-.02,.02,x1+.03,y1+.02,height+.03,'silver')
    elif ref=='AE1':
        kind='illustrative spring antenna';height=20
        x,y=pads[0]['xy'];mesh.tube((x,y,-2),(x,y,2),.3,'copper')
        radius=1.4;turns=8;segments=240
        mesh.tube((x,y,2),(x+radius,y,2),.3,'copper')
        prior=(x+radius,y,2)
        for i in range(1,segments+1):
            angle=2*math.pi*turns*i/segments
            next_point=(x+radius*math.cos(angle),y+radius*math.sin(angle),2+18*i/segments)
            mesh.tube(prior,next_point,.3,'copper',8);prior=next_point
    elif re.fullmatch(r'J(?:1[2-9]|2[0-5])',ref):
        kind='Metz screw terminal';height=6.0
        # Leave a real wire-entry cavity on local -Y. Footprint rotations
        # point this face toward the corresponding board edge.
        hole_left, hole_right = cx-.9, cx+.9
        mesh.box(x0,y0,.2,x1,y1,1.1,'silver')
        mesh.box(x0,y0,3.1,x1,y1,4.9,'silver')
        mesh.box(x0,y0,1.1,hole_left,y1,3.1,'silver')
        mesh.box(hole_right,y0,1.1,x1,y1,3.1,'silver')
        mesh.box(hole_left,y0+1.5,1.1,hole_right,y1,3.1,'silver')
        mesh.box(hole_left,y0+1.45,1.1,hole_right,y0+1.5,3.1,'black')
        mesh.tube((cx,cy,4.9),(cx,cy,5.85),1.5,'silver',24)
        mesh.box(cx-1.32,cy-.16,5.84,cx+1.32,cy+.16,5.88,'black')
        for pad in pads:
            x,y=pad['xy'];mesh.tube((x,y,-3),(x,y,.3),.55,'silver')
    else:
        raise ValueError(f'No original approximation defined for {ref}')
    mesh.save(destination,ref)
    return {'classification':'original_parametric_approximation', 'kind':kind,
            'xy_evidence':'Current PCB F.Fab body bounds and native pad positions',
            'body_bounds_model_mm':bounds, 'illustrative_height_mm':height,
            'height_and_detail_evidence':'Illustrative; not manufacturer-qualified dimensions',
            'path':str(destination),'sha256':sha(destination), 'vrml_coordinate_mm_per_unit':2.54,
            'model_scale':[1,1,1], 'use':'Visual approximation; not mechanical or manufacturing validation'}


def tokenized_without_models(text):
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()]+',text)
    result=[];i=0
    while i<len(tokens):
        if tokens[i]=='(' and i+1<len(tokens) and tokens[i+1]=='model':
            depth=0
            while i<len(tokens):
                depth += (tokens[i]=='(')-(tokens[i]==')');i+=1
                if depth==0:break
        else:result.append(tokens[i]);i+=1
    return result



def is_purchased(fp):
    fields = {field.GetName(): field.GetText() for field in fp.GetFields()}
    pads = list(fp.Pads())
    mechanical = pads and all(pad.GetAttribute() == p.PAD_ATTRIB_NPTH for pad in pads)
    return not (fp.IsExcludedFromBOM() or fp.IsDNP() or mechanical
                or str(fp.GetFPID().GetLibNickname()) == 'MountingHole'
                or fields.get('Assembly') == 'PCB copper; no purchased part'
                or fp.GetReference().startswith('TP'))


def resolve_model(filename, source_dir, model_dirs, cache, download):
    """Resolve installed models, optionally caching a pinned library download."""
    match = re.fullmatch(r'\$\{KICAD\d+_3DMODEL_DIR\}/(.+)', filename)
    relative = match.group(1) if match else None
    if relative:
        if '..' in Path(relative).parts:
            raise ValueError('Invalid library model path')
        roots = [*model_dirs, *[Path(value) for key, value in os.environ.items()
                               if re.fullmatch(r'KICAD\d+_3DMODEL_DIR', key)],
                 Path('/usr/share/kicad/3dmodels'),
                 Path('/usr/local/share/kicad/3dmodels'), cache]
        for root in roots:
            candidate = root / relative
            if candidate.is_file():
                return candidate.resolve()
        if download:
            url = ('https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/9.0.9/'
                   + urllib.parse.quote(relative, safe='/'))
            destination = cache / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read()
                if not data.startswith((b'ISO-10303', b'#VRML')):
                    raise ValueError('Unexpected model download format')
                destination.write_bytes(data)
                return destination.resolve()
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
    else:
        expanded = os.path.expandvars(filename.replace('${KIPRJMOD}', str(source_dir)))
        path = Path(expanded).expanduser()
        if not path.is_absolute():
            path = source_dir / path
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(f'Missing 3D model: {filename}. Install KiCad 3D libraries, '
                            'set KICAD9_3DMODEL_DIR, or use --download-models.')


class Assembly:
    """Original module geometry in board XY, mm above the front surface."""
    def __init__(self, footprint):
        self.fp = footprint
        self.mesh = Mesh()

    def xy(self, x, y):
        return local_point(self.fp, p.VECTOR2I(p.FromMM(x), p.FromMM(y)))

    def box(self, x0, y0, z0, x1, y1, z1, material):
        points = [self.xy(x, y) for x in (x0, x1) for y in (y0, y1)]
        self.mesh.box(min(x for x, y in points), min(y for x, y in points), z0,
                      max(x for x, y in points), max(y for x, y in points), z1, material)

    def cylinder(self, x, y, z0, z1, radius, material):
        lx, ly = self.xy(x, y)
        self.mesh.tube((lx, ly, z0), (lx, ly, z1), radius, material, 24)

    def pins(self, pads, pcb_bottom):
        for pad in pads:
            x, y = native_position(pad.GetPosition())
            self.box(x-.32, y-.32, 5.8, x+.32, y+.32, pcb_bottom+1.9, 'gold')
            self.box(x-1.1, y-1.1, 8.5, x+1.1, y+1.1, pcb_bottom, 'black')
            self.cylinder(x, y, pcb_bottom+1.6, pcb_bottom+1.67, .82, 'gold')

    def chip(self, x, y, z, width=3, depth=3):
        self.box(x-width/2,y-depth/2,z,x+width/2,y+depth/2,z+.9,'black')
        for dy in (-depth/3, 0, depth/3):
            for side in (-1, 1):
                cx=x+side*(width/2+.25)
                self.box(cx-.28,y+dy-.16,z,cx+.28,y+dy+.16,z+.35,'silver')


def module_models(fps, models, pcb_bottom=11.0):
    """Five selectable module illustrations. Variant details/heights are assumed."""
    COLORS.update(pcb=(.055,.10,.085), blue=(.025,.19,.36), glass=(.012,.025,.035),
                  display=(.025,.055,.065),white=(.86,.86,.82),sensor=(.84,.86,.82))
    z=pcb_bottom; top=z+1.6
    first=fps['J6'].GetPosition(); x,y=native_position(first)
    if abs(native_position(fps['J7'].GetPosition())[0]-x-22.86)>1e-5:
        raise ValueError('Unexpected DevKit socket spacing; update module geometry')
    if abs(fps['J6'].GetOrientationDegrees())>1e-5:
        raise ValueError('Unexpected DevKit rotation; update module geometry')
    left,upper=x-1.27,y-1.575;right,lower=left+25.4,upper+53.6
    devkit=Assembly(fps['J6']);devkit.box(left,upper,z,right,lower,top,'pcb')
    devkit.pins([*fps['J6'].Pads(), *fps['J7'].Pads()],z)
    for cx in (left+6,right-6):
        cy=lower-3.3
        devkit.box(cx-4.3,cy-3.5,top,cx+4.3,cy+3.7,top+3.1,'silver')
        devkit.box(cx-3.65,cy+3.71,top+.45,cx+3.65,cy+3.77,top+2.55,'black')
        cy=upper+42
        devkit.box(cx-2.1,cy-1.8,top,cx+2.1,cy+1.8,top+1.2,'silver')
        devkit.cylinder(cx,cy,top+1.2,top+1.85,1.2,'black')
    devkit.chip(x+11.43,upper+35,top,5,5)
    devkit.chip(x+11.43,upper+26,top,3,3)
    # WROOM envelope and antenna are original illustrations, not vendor CAD.
    mx=left+12.7
    devkit.box(mx-9,upper-6.5,top,mx+9,upper+21,top+.8,'pcb')
    devkit.box(mx-9,upper+1,top+.8,mx+9,upper+21,top+3.2,'silver')
    for i in range(5):
        xx=mx-7+i*3.2
        devkit.box(xx,upper-5.5,top+.81,xx+.45,upper-.3,top+.84,'gold')
        if i<4:
            yy=upper-5.5 if i%2==0 else upper-.75
            devkit.box(xx,yy,top+.81,xx+3.65,yy+.45,top+.84,'gold')
    oled=Assembly(fps['J3']);oled.box(11,1,z,39,29,top,'blue')
    oled.pins(list(fps['J3'].Pads()),z)
    oled.box(12,6.5,top,38,24.5,top+.6,'black')
    oled.box(12.5,7,top+.6,37.5,24,top+1,'glass')
    oled.box(14,9.7,top+1,36,20.7,top+1.03,'display')
    for cx,cy in ((13,3),(37,3),(13,27),(37,27)):
        oled.cylinder(cx,cy,.15,z,1.7,'white')
        oled.cylinder(cx,cy,top+.02,top+.75,1.65,'white')
    rtc=Assembly(fps['J2']);rtc.box(59.5,.5,z,75.5,24,top,'blue')
    rtc.pins(list(fps['J2'].Pads()),z);rtc.chip(64,7,top,3.5,4)
    rtc.cylinder(67.5,16.5,top,top+2.1,5.8,'silver')
    dht=Assembly(fps['J1']);dht.box(79.5,.5,z,90.5,17,top,'blue')
    dht.pins(list(fps['J1'].Pads()),z);dht.box(82,7,top,88,14,top+2.6,'sensor')
    for cy in (8,9.3,10.6,11.9,13.2):
        dht.box(82.5,cy,top+2.6,87.5,cy+.45,top+2.62,'black')
    rf=Assembly(fps['J4']);rf.box(1.5,12.5,z,10,26.5,top,'pcb')
    rf.pins(list(fps['J4'].Pads()),z);rf.chip(7,19,top,2.6,4)
    rf.box(5.5,23,top,8.5,25,top+1,'silver')
    result=[]
    for name,label,assembly in [('esp32-c5','ESP32-C5 DevKit',devkit),('oled','OLED',oled),
                                ('rtc','RTC',rtc),('dht20','DHT20',dht),('rf433','433 MHz receiver',rf)]:
        identifier='module-'+name; destination=models/(identifier+'.wrl')
        assembly.mesh.save(destination,'Illustrative '+label)
        model=p.FP_3DMODEL();model.m_Filename=str(destination.resolve())
        index=len(assembly.fp.Models());assembly.fp.Add3DModel(model)
        result.append({'id':identifier,'label':label,'kind':'module','node':identifier,
                       'approximate':True,'defaultVisible':True,'ref':assembly.fp.GetReference(),
                       'model_index':index,'path':str(destination.resolve())})
    return result


def prepare_models(source, output, model_dirs=(), download_models=False):
    """Return a prepared PCB and selectable model metadata; never modify source."""
    source=Path(source).resolve();output=Path(output).resolve()
    if output==source.parent or source.is_relative_to(output):
        raise ValueError('Use a separate build directory, not the source directory')
    output.mkdir(parents=True,exist_ok=True);models=output/'models';models.mkdir(exist_ok=True)
    source_hash=sha(source);board=p.LoadBoard(str(source));assignments=[];entries=[]
    project_root=Path(__file__).resolve().parents[1]
    cache=project_root/'build/3dmodels'
    for fp in sorted(board.GetFootprints(),key=lambda f:f.GetReference()):
        if not is_purchased(fp):
            continue
        ref=fp.GetReference();original=list(fp.Models());paths=[];approximate=False
        if ref in {f'J{i}' for i in range(12,26)} or not original:
            destination=models/(ref+'.wrl');make_model(fp,destination)
            fp.Models().clear();model=p.FP_3DMODEL();model.m_Filename=str(destination)
            fp.Add3DModel(model);paths=[destination];approximate=True
        else:
            fp.Models().clear()
            for index,model in enumerate(original):
                if not model.m_Show:
                    continue
                path=resolve_model(str(model.m_Filename),source.parent,list(model_dirs),cache,download_models)
                # Unique reference-based names let the converter retain selection groups.
                destination=models/(ref+('-'+str(index) if index else '')+path.suffix)
                shutil.copyfile(path,destination);model.m_Filename=str(destination)
                fp.Add3DModel(model);paths.append(destination)
        if not paths:
            raise ValueError('No visible models for '+ref)
        row={'id':ref,'label':ref+' · '+fp.GetValue(),'kind':'carrier','node':ref,
             'approximate':approximate,'defaultVisible':True}
        if ref in {f'J{i}' for i in range(12,26)}:
            angle=math.radians(fp.GetOrientationDegrees())
            # Local model -Y becomes (sin(angle),cos(angle)) in front PCB XY.
            row['wireEntryDirectionPcbXY']=[round(math.sin(angle)),round(math.cos(angle))]
        assignments.append(row)
        entries.extend({'id':ref,'ref':ref,'model_index':index,'path':str(path.resolve())}
                       for index,path in enumerate(paths))
    fps={fp.GetReference():fp for fp in board.GetFootprints()}
    modules=module_models(fps,models)
    assignments.extend({k:v for k,v in row.items() if k not in {'path','model_index','ref'}} for row in modules)
    entries.extend(modules)
    target=output/source.name
    if p.SaveBoard(str(target),board) is False:
        raise ValueError('Cannot save 3D snapshot')
    for suffix in ('.kicad_pro','.kicad_dru'):
        path=source.with_suffix(suffix)
        if path.is_file():
            shutil.copyfile(path,target.with_suffix(suffix))
    if sha(source)!=source_hash:
        raise RuntimeError('Source changed while preparing 3D snapshot')
    if tokenized_without_models(source.read_text())!=tokenized_without_models(target.read_text()):
        raise RuntimeError('Prepared PCB changed data beyond model references')
    return {'pcb':target,'components':assignments,'model_entries':entries,
            'sourcePcbSha256':source_hash,'upAxis':'Z',
            'assumptions':{
                'carrier':'Generic KiCad package models and original parametric approximations.',
                'modules':'Original illustrations. Module variants and 11 mm PCB underside height are assumed.',
                'dimensions':'ESP32-C5 DevKit v1.2 PCB envelope: 25.4 x 53.6 mm; headers 22.86 mm apart.',
                'qualification':'Visual assembly only; not a mechanical fit or clearance qualification.'}}
