"""Create a self-authored directional normal-map fixture for UV verification."""
import argparse, hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();root=Path(a.output);asset=root/'DirectionalFixture';asset.mkdir(parents=True,exist_ok=False)
n=512;x=np.arange(n)[None,:];y=np.arange(n)[:,None]
# Unequal horizontal and vertical waves break 90-degree symmetry. The analytic normal
# is a height derivative in tangent coordinates, not a decorative random normal map.
h=.022*np.sin(2*np.pi*x/64)+.007*np.sin(2*np.pi*y/113)
dx=np.broadcast_to(.022*2*np.pi/64*np.cos(2*np.pi*x/64)*80,(n,n));dy=np.broadcast_to(.007*2*np.pi/113*np.cos(2*np.pi*y/113)*80,(n,n));normal=np.stack([-dx,-dy,np.ones((n,n))],axis=2);normal/=np.linalg.norm(normal,axis=2,keepdims=True)
color=np.full((n,n,3),150,dtype=np.uint8);rough=np.full((n,n),150,dtype=np.uint8);maps={'color':color,'normal':np.uint8(np.clip((normal*.5+.5)*255,0,255)),'roughness':rough}
records={}
for key,values in maps.items():
 path=asset/(key+'.jpg');Image.fromarray(values).save(path,quality=100,subsampling=0);data=path.read_bytes();records[key]={'member':path.name,'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
record={'schema_version':1,'asset_id':'DirectionalFixture','material_id':'authored/directional-fixture','provider':'this study','license':'CC0-1.0','normal_convention':'OpenGL','maps':records}
(root/'DirectionalFixture.json').write_text(json.dumps(record,indent=2))
