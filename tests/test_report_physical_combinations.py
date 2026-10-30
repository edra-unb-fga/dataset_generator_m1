from pathlib import Path
import importlib.util, json
import numpy as np
from PIL import Image
spec=importlib.util.spec_from_file_location('physical_report',str(Path(__file__).resolve().parents[1] / 'scripts/report_physical_combinations.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_metrics_masks_foreground_and_background():
 a=Image.fromarray(np.zeros((2,2,3),dtype=np.uint8))
 b=Image.fromarray(np.array([[[30]*3,[10]*3],[[10]*3,[10]*3]],dtype=np.uint8))
 masks={'visible':np.array([[[True,False],[False,False]]]),'full':np.ones((1,2,2),dtype=bool)}
 result=m.compare_images(a,b,masks,masks)
 assert result['masks_equal'] and result['rgb_mae']==15 and result['foreground_rgb_mae']==30 and result['background_rgb_mae']==10
 assert m.compare_images(a,Image.new('RGB',(3,3)),masks,masks)['rgb_mae'] is None
 assert m.crop_box({'visible':np.zeros((0,2,2),bool)},(2,2)) is None

def test_portable_and_missing_outputs(tmp_path):
 root=tmp_path/'results';root.mkdir();cells=[{'id':'baseline','jobs':['000-core-fast']},{'id':'candidate','jobs':['000-core-fast']},{'id':'missing','jobs':['000-core-fast']}]
 (root/'matrix.json').write_text(json.dumps({'cells':cells}))
 (root/'summary.json').write_text(json.dumps({'status':'complete','records':[]}))
 for cell,pix in [('baseline',0),('candidate',20)]:
  path=root/'cells'/cell/'scenes'/'000-core-fast';path.mkdir(parents=True)
  Image.new('RGB',(32,32),(pix,pix,pix)).save(path/'rgb.png')
  mask=np.zeros((1,32,32),bool);mask[:,10:20,10:20]=True
  np.savez(path/'masks.npz',visible=mask,full=mask)
  (path/'result.json').write_text(json.dumps({'status':'accepted','image':'/content/an/irrelevant/path'}))
 output=tmp_path/'report.html';result=m.build(root,output)
 assert result['metrics'][1]['rgb_mae']==20
 assert result['metrics'][1]['foreground_rgb_mae']==20
 assert result['metrics'][2]['status']=='missing'
 assert 'data:image/jpeg;base64,' in output.read_text()
 assert '/content/an/irrelevant/path' not in output.read_text()
 assert output.with_suffix('.metrics.json').exists()
