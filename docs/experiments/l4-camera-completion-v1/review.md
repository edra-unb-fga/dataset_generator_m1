Single-reviewer visual assessment (not an independent review):

- The corrected scenes keep the tested pads inside the walls. The earlier indoor and outdoor 002 cases were rejected after eight support-floor retries; both are accepted in the adjusted development run. All paired environment masks in the tested ordinary scenes now match their open controls.
- The ground textures and panel perspective are coherent in many views, and the motion treatment visibly softens moving-camera images. The appearance is still recognizably synthetic: targets have very clean artwork and edges, little evident wear or contact detail, and some surfaces look smooth or uniformly lit.
- The indoor and outdoor geometry is a bounded prototype, not convincing environment reconstruction. Where visible, walls can appear as simple straight strips or wedges; some held-out overhead views show no walls at all. These images do not establish convincing room context or general wall coverage.
- A frame-zero sharp mask remains a deliberate reference in the motion examples. It does not follow every blurred RGB boundary. Lens distortion changes the mapping, so distorted masks should not be expected to equal the undistorted controls pixel for pixel.
- The six development and three held-out ordinary viewpoints are too few to validate the intended camera-angle distribution. The current 1280px phase uses two scenes per condition. No real images, detector results, or calibrated material/camera measurements were available.
- Keep the environment variants and experimental 2D compositing opt-in. Further real-reference assessment, a wider held-out viewpoint sample, natural scene context and real-reference review are needed before claiming realism or model-transfer improvement.

Independent visual review (GPT-6.1 Terra, using the separately prepared review sheets):

- Open-view is the strongest conservative candidate for further testing: panels appear planar with
  their backgrounds and geometric outlines generally follow their edges. This is not a realism or
  model-transfer qualification.
- Indoor and outdoor changes are subtle in many images; visible wall edges often read as flat gray
  wedges or dark strips, rather than convincing room geometry. One broad diagonal indoor patch reads
  like an overlay rather than clearly motivated lighting.
- The grass texture appears coarse beside very clean, saturated panels, with limited visible contact
  detail. Concrete and dark ground appear more coherent but visually flat. The diagnostic white-bar
  occluder is useful for geometry checks, not natural-looking context.
- Motion affects both ground and markers in a plausible direction, but warped or doubled marker
  features and sharp geometric contours differ from blurred RGB boundaries. Treat this as an
  augmentation study, not validated physical realism.
- Six development and three held-out ordinary scenes are too few to promote a variant as demonstrably
  realistic. Real references, larger samples and downstream model tests are still necessary.

Independent review of the 32-versus-128 sample sheet: at the displayed scale the paired scenes look
very similar, and the wall edges and strong motion smear persist. The reviewer could not confidently
identify a meaningful visual improvement from 128 samples in this sheet. This observation covers one
scene per variant in a JPEG montage; it does not prove equivalence or exclude subtle native-resolution
noise differences or different outcomes for other scenes.
