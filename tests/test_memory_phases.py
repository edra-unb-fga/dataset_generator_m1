from PIL import Image

from dataset_generator_m1.config import load_profile
from dataset_generator_m1.execution import plan_execution
from dataset_generator_m1.models import BackgroundRecipe, RecipeNode, RecipeCatalog, ExecutionConfig


def with_recipes(recipes):
    value=load_profile('examples/configs/landing-pad_minimal.yaml')
    profile=value.profile.model_copy(update={'execution':ExecutionConfig(native_threads=1)})
    return value.model_copy(update={'profile':profile,'recipes':RecipeCatalog(schema_version=1,recipes=recipes)})


def chain(length):
    nodes=[RecipeNode(id='asset',op='sample_asset')]
    for i in range(length):
        nodes.append(RecipeNode(id=f'canvas{i}',op='resize_crop',inputs={'image':'asset' if i==0 else f'canvas{i-1}'}))
    return BackgroundRecipe(nodes=tuple(nodes),output=f'canvas{length-1}')


def test_serial_graph_depth_does_not_accumulate_dead_arrays():
    short=plan_execution(with_recipes({'chain':chain(4)}))
    long=plan_execution(with_recipes({'chain':chain(40)}))
    assert long.estimated_peak_bytes<=short.estimated_peak_bytes*1.05


def test_live_branches_cost_more_than_dead_chain():
    nodes=[RecipeNode(id='asset',op='sample_asset')]
    for i in range(8):nodes.append(RecipeNode(id=f'branch{i}',op='resize_crop',inputs={'image':'asset'}))
    previous='branch0'
    for i in range(1,8):
        name=f'merge{i}';nodes.append(RecipeNode(id=name,op='palette_transfer',inputs={'image':previous,'palette':f'branch{i}'}));previous=name
    wide=BackgroundRecipe(nodes=tuple(nodes),output=previous)
    assert plan_execution(with_recipes({'wide':wide})).estimated_peak_bytes>plan_execution(with_recipes({'chain':chain(8)})).estimated_peak_bytes


def test_small_foreground_does_not_add_to_larger_background_phase(tmp_path):
    value=with_recipes({'chain':chain(4)})
    def estimate(size):
        path=tmp_path/f'fg{size}.png';Image.new('RGBA',(size,size)).save(path)
        assets=value.profile.assets.model_copy(update={'foregrounds':value.profile.assets.foregrounds.model_copy(update={'paths':(str(path),)})})
        return plan_execution(value.model_copy(update={'profile':value.profile.model_copy(update={'assets':assets})}))
    assert estimate(8).estimated_peak_bytes==estimate(32).estimated_peak_bytes


def test_early_output_stays_live_through_later_expensive_nodes():
    nodes=[RecipeNode(id='source',op='sample_asset'),
           RecipeNode(id='first',op='resize_crop',inputs={'image':'source'}),
           RecipeNode(id='second',op='resize_crop',inputs={'image':'source'}),
           RecipeNode(id='a',op='palette_transfer',inputs={'image':'first','palette':'second'}),
           RecipeNode(id='b',op='palette_transfer',inputs={'image':'a','palette':'second'})]
    early=BackgroundRecipe(nodes=tuple(nodes),output='first')
    late=BackgroundRecipe(nodes=tuple(nodes),output='b')
    assert plan_execution(with_recipes({'r':early})).estimated_peak_bytes>plan_execution(with_recipes({'r':late})).estimated_peak_bytes


def test_extreme_foreground_aspect_accounts_for_resize(tmp_path):
    value=with_recipes({'r':chain(4)})
    def estimate(dimensions):
        path=tmp_path/f'{dimensions[0]}-{dimensions[1]}.png';Image.new('RGBA',dimensions).save(path)
        assets=value.profile.assets.model_copy(update={'foregrounds':value.profile.assets.foregrounds.model_copy(update={'paths':(str(path),)})})
        return plan_execution(value.model_copy(update={'profile':value.profile.model_copy(update={'assets':assets})}))
    assert estimate((2,4000)).estimated_peak_bytes>estimate((100,100)).estimated_peak_bytes
