# New Architecture for the Synthetic Data Generation Pipeline

## Pipeline:
 Background Generation + Foreground Generation (with the applicable affine transformations for each) -> Perspective Transformations (applied to both the foreground as well as the background with the same parameters for a consistent coplanar view of the composition) -> Assembly + Annotation (annotation will be done with the data forwarded by the previous stages of the pipeline combined with the assembly information) -> Transformations (color, lighting, filters, etc) -> Center crop -> Final image

## Implementation details

### Parameterization and Control:
Parametric control of all relevant variables (probability of applying a filter, range of values for the filters, range of values for the transformations, range of allowable crop size, range of allowable rotation angles, range of possible amounts of foreground instances on a given image, etc) divided by stages and organized by types, control is to be done through a config yaml file for each pipeline (one for manometro and another one for landing).

### Filters and Transformations Implementation:
Use of Albumentations Image-Only Transformations [Image-Only Transformations Albumentations Transform](explore.albumentations.ai) for filters and transformations, both to background, foreground, and to the combination of the two (after assembly). Affine transformations, perspective transformations, and annotations (bounding boxes) will be done with a opencv2, pillow or whatever is seen as best during the implementation.

### CLI and API: 
The pipeline should be able to be run a CLI command, with the possibility of selecting the type of dataset (manometro or landing), the config file to use, the number of images to generate, the output directory and whether to generate some debug images in a directory inside that output directory before the full final output (annotated images for the user to check a sample of what they are generating).

## Steps

### Background Generation:
Background generation will use tiling (one center cell of the chosen background and its 8 neighbors), then the application of any filters (color, contrast, brightness, saturation, blur, noise etc), horizontal and vertical flips, and affine transformations (rotation, scaling, translation). Done in one specific thread, it should send the generated background to the main thread, which will then use it to assemble the image. Backgrounds cells will be taken from the "backgrounds" directory by default, but there will be the option to use a custom directory.

### Foreground Generation:
Foreground generation will be done in a separate thread, which will possibly apply filters and transformations to the foreground image (with some clear limitations, no flips, small noise, small blur, and rotation preserving information (there will be no cropping on the method that rotates a square image, it will have a bigger bounding box, and there will be cropping on the method that rotates an image for a circular object, preserving a bounding box tight to the actual object on both cases), highlights, plasma shadow, etc). The generated foreground and the information about the method used for rotation (circle or square) will then be sent to the main thread, which will use the given foregrounds to assemble images. The possible foregrounds will either be pre generated images from the "new foregrounds\manometro_foregrounds" directory (for when we want to create a manometro dataset) that should use the square rotation method, or from the pre generated "foregrounds\landing_foregrounds" directory (for when we want to create a landing dataset), that should use the circle rotation method.

### Perspective Transformations:
Perspective transformations will be applied to both the foreground and the background with the same parameters for a consistent coplanar view of the composition (same tilt for the ground and for the things on top of it). These will still be done in the respective threads for the foreground and background generation with parameters that are sent from the main thread, this way both the foreground and background generated for a given image should have the same perspective.

### Assembly:
The main thread will be responsible for assembling the final image, which will involve combining the generated background and foreground images, it will ask for and receive the generated foregrounds (and the data necessary to generate the yolo format bounding boxes annotation .txt file) choose their sizes and position, and the tiled background (with whatever information is necessary to do a legal crop). It will also handle any necessary constraints, such as the actual size of the final image (it will be scaled probabilistically but be centered on the center of the generated background and have at most the size and resolution of the original background image before tiling), the foreground images (there can be multiple instances pasted into the final image) should all be contained within the crop (the random number for the crop is selected before pasting the foregrounds, so the foregrounds should be pasted in a way that they are all contained within the crop).

### Annotation:
The main thread will also be responsible for generating the annotation .txt file in yolo format, which will be done with the data forwarded by the previous stages of the pipeline combined with the assembly information (the position of the foregrounds on the final image, the size of the final image, and the parameters used for the perspective transformation that affect the bounding boxes). The annotation will be generated just after the cut of the image, so that it can take into account any necessary constraints (such as all foregrounds being contained within the crop).

### Final Transformations (Filters, color, lighting, etc. No afine and No perspective transformations):
After each image is assembled and cut, the main thread can still apply some filters (that affect the foreground and background together, such as color, contrast, brightness, saturation, blur, noise, highlights, shadows, fog etc)


## Detailed config file parameters:

### General parameters:

- `dataset_type`: str, either "manometro" or "landing", this will determine the type of foregrounds to use and the type of behavior of foreground rotation (square or circle method).
- `num_images`: int, number of images to generate.
- `output_dir`: str, path to the directory where the generated images and annotations will be saved.
- `debug`: int or None, whether to generate debug images for a sample of the generated images and how many (if int, the number of debug images to generate, if None, no debug images will be generated).
- `debug_dir`: str, path to the directory where the debug images will be saved (inside the output directory), only used if `debug` is not None.
- `backgrounds_dir`: str or list, path to the directory where the background images are located or a list of paths, default is "backgrounds".

### Affine Transformations Augmentation and geometric parameters:

- `perspective_transformations`: dict, parameters for the perspective transformations to apply to both the background and foreground on a given image and the probability of applying them.
  - `scale_range`: tuple of float, range of scaling factors for the perspective transformation (min, max).
  - `shear_range`: tuple of float, range of shear factors for the perspective transformation (min, max).
  - `probability`: float, probability of applying the perspective transformation.

- `background_affine_transformations`: dict, parameters for the affine transformations to apply to the background images and the probability of applying them.
  - `affine_transformations`: dict, parameters for the affine transformations to apply to the background and foreground images and the probability of applying them.
    - `rotation`: dict, parameters for the rotation transformation.
      - `angle_range`: tuple of int, range of angles for the rotation (min, max).
      - `probability`: float, probability of applying the rotation transformation.
    - `scaling`: dict, parameters for the scaling transformation.
      - `scale_range`: tuple of float, range of scaling factors (min, max).
      - `probability`: float, probability of applying the scaling transformation.
    - `translation`: dict, parameters for the translation transformation.
      - `translate_range`: tuple of int, range of translation in fraction of image size (min, max).
      - `probability`: float, probability of applying the translation transformation.

- `foreground_affine_transformations`: dict, parameters for the affine transformations to apply to the foreground images and the probability of applying them.
  - `rotation`: dict, parameters for the rotation transformation.
    - `angle_range`: tuple of int, range of angles for the rotation (min, max).
    - `probability`: float, probability of applying the rotation transformation.

- `foreground_scale_range`: tuple of float, range of scaling factors for the foreground images as a fraction of the image size (min, max).

### Image-Only Transformations Albumentations parameters:

- `background_filters`: dict, parameters for the filters to apply to the background images and the probability of applying them.
  - `ColorFilters`: dict, parameters for the color filters to apply to the background images and the probability of applying them.
    - [`HueSaturationValue`](https://explore.albumentations.ai/transform/HueSaturationValue): dict, parameters for the HueSaturationValue filter and probability of applying it.
      - `hue_shift_range`: tuple of int, range of values for the hue shift, should be in range of -180 and 180 (min, max).
      - `sat_shift_range`: tuple of int, range of values for the saturation shift, should be in range of -255 and 255 (min, max).
      - `val_shift_range`: tuple of int, range of values for the value shift, should be in range of -255 and 255 (min, max).
      - `probability`: float, probability of applying the HueSaturationValue filter.
    - [`RandomBrightnessContrast`](https://explore.albumentations.ai/transform/RandomBrightnessContrast): dict, parameters for the RandomBrightnessContrast filter and probability of applying it.
      - `brightness_range`: tuple of float, range of values for the brightness shift, should be in range of -1 and 1 (min, max).
      - `contrast_range`: tuple of float, range of values for the contrast shift, should be in range of -1 and 1 (min, max).
      - `brightness_by_max`: bool, whether to use the maximum brightness value for the brightness shift.
      - `ensure_safe_output`: bool, whether to ensure that the output values are in the valid range (0-255).
      - `probability`: float, probability of applying the RandomBrightnessContrast filter.
  - `BlurAndNoiseFilters`: dict, parameters for the BlurAndNoiseFilters to apply to the background images and the probability of applying them.
    - [`GaussianBlur`](https://explore.albumentations.ai/transform/GaussianBlur): dict, parameters for the GaussianBlur filter and probability of applying it.
      - `blur_limit`: tuple of int, range of values for the kernel size of the Gaussian blur (min, max).
      - `sigma_limit`: tuple of float, range of values for the sigma of the Gaussian blur (min, max).
      - `probability`: float, probability of applying the GaussianBlur filter.
    - [`GaussNoise`](https://explore.albumentations.ai/transform/GaussNoise): dict, parameters for the GaussNoise filter and probability of applying it.
      - `std_range`: tuple of float, range of values for the standard deviation of the Gaussian noise, should be between 0 and 1 (min, max).
      - `mean_range`: float, range of noise as a fraction of max, should be between -1 and 1 (min, max).
      - `per_channel`: bool, if true sample noise per channel; else sample noise for all True or False.
      - `probability`: float, probability of applying the GaussNoise filter.

- `foreground_filters`: dict, parameters for the filters to apply to the foreground images and the probability of applying them.
  - `ColorFilters`: dict, parameters for the color filters to apply to the foreground images and the probability of applying them.  
    - [`HueSaturationValue`](https://explore.albumentations.ai/transform/HueSaturationValue): dict, parameters for the HueSaturationValue filter and probability of applying it.  
      - `hue_shift_range`: tuple of int, range of values for the hue shift, should be in range of -180 and 180 (min, max).
      - `sat_shift_range`: tuple of int, range of values for the saturation shift, should be in range of -255 and 255 (min, max).
      - `val_shift_range`: tuple of int, range of values for the value shift, should be in range of -255 and 255 (min, max).
      - `probability`: float, probability of applying the HueSaturationValue filter.  
  - `BlurAndNoiseFilters`: dict, parameters for the BlurAndNoiseFilters to apply to the foreground images and the probability of applying them.
    - [`AdditiveNoise`](https://explore.albumentations.ai/transform/AdditiveNoise): dict, parameters for the AdditiveNoise filter and probability of applying it.
      - `noise_type`: str, type of noise distribution to use, either "uniform", "gaussian", "laplace", or "beta".
      - `spatial_mode`: str, how to generate and apply the noise, either "constant", "per_pixel", or "shared".
      - `noise_params`: dict or None, parameters for the chosen noise distribution.
      - `probability`: float, probability of applying the AdditiveNoise filter.
  - `AtmosphericEffectsFilters`: dict, parameters for the atmospheric effects and miscellaneous filters to apply to the foreground images and the probability of applying them.
    - [`PlasmaShadow`](https://explore.albumentations.ai/transform/PlasmaShadow): dict, parameters for the PlasmaShadow filter and probability of applying it.
      - `shadow_intensity_range`: tuple of float, range of values for the shadow intensity, should be between 0 and 1 (min, max).
      - `plasma_size`: int, size of the initial plasma pattern grid.
      - `roughness`: float, controls how quickly the plasma noise amplitude increases, should be greater than 0.
      - `probability`: float, probability of applying the PlasmaShadow filter.
    - [`PlasmaBrightnessContrast`](https://explore.albumentations.ai/transform/PlasmaBrightnessContrast): dict, parameters for the PlasmaBrightnessContrast filter and probability of applying it.
      - `brightness_range`: tuple of float, range of values for the spatial brightness adjustment, should be between -1 and 1 (min, max).
      - `contrast_range`: tuple of float, range of values for the spatial contrast adjustment, should be between -1 and 1 (min, max).
      - `plasma_size`: int, size of the initial plasma pattern grid.
      - `roughness`: float, controls how quickly the plasma noise amplitude increases, should be greater than 0.
      - `probability`: float, probability of applying the PlasmaBrightnessContrast filter.
    - [`RandomSunFlare`](https://explore.albumentations.ai/transform/RandomSunFlare): dict, parameters for the RandomSunFlare filter and probability of applying it.
      - `flare_roi`: tuple of float, region where the sun flare can appear in relative coordinates (x_min, y_min, x_max, y_max), should be in range of 0 and 1.
      - `src_radius`: int, radius of the sun circle in pixels.
      - `src_color`: tuple of int, color of the sun in RGB format.
      - `angle_range`: tuple of float, range of angles for the flare direction, should be in range of 0 and 1 (min, max).
      - `num_flare_circles_range`: tuple of int, range for the number of flare circles to generate (min, max).
      - `method`: str, method to use for generating the sun flare, either "overlay" or "physics_based".
      - `probability`: float, probability of applying the RandomSunFlare filter.
  
- `final_filters`: dict, parameters for the filters to apply to the final images and the probability of applying them.
  - `ColorFilters`: dict, parameters for the color filters to apply to the final images and the probability of applying them.
    - [`RandomGamma`](https://explore.albumentations.ai/transform/RandomGamma): dict, parameters for the RandomGamma filter and probability of applying it.
      - `gamma_range`: tuple of float, range of values for the gamma shift in percentage centered around 100 (min, max).
      - `probability`: float, probability of applying the RandomGamma filter.
    - [`PlankianJitter`](https://explore.albumentations.ai/transform/PlankianJitter): dict, parameters for the PlankianJitter filter and probability of applying it.
      - `mode`: str, mode to use for the PlankianJitter filter, either "blackbody" or "cied".
      - `temperature_range`: tuple of int, range of values for the temperature shift, should be in range of 3000 and 15000 (min, max).
      - `sampling_method`: str, method to use for sampling the temperature shift, either "uniform" or "gaussian".
      - `probability`: float, probability of applying the PlankianJitter filter.
  - `BlurAndNoiseFilters`: dict, parameters for the BlurAndNoiseFilters to apply to the final images and the probability of applying them.
    - [`SaltAndPepper`](https://explore.albumentations.ai/transform/SaltAndPepper): dict, parameters for the SaltAndPepper filter and probability of applying it.
      - `amount_range`: tuple of float, range for the total amount of salt and pepper noise, should be between 0 and 1 (min, max).
      - `salt_vs_pepper_range`: tuple of float, range for the ratio of salt noise to pepper noise, should be between 0 and 1 (min, max).
      - `probability`: float, probability of applying the SaltAndPepper filter.
    - [`MotionBlur`](https://explore.albumentations.ai/transform/MotionBlur): dict, parameters for the MotionBlur filter and probability of applying it.
      - `blur_range`: tuple of int, range of values for the motion blur kernel size, both values should be at least 3 (min, max).
      - `allow_shifted`: bool, whether to allow random shifts of the motion blur kernel position.
      - `angle_range`: tuple of float, range of possible angles for the motion blur line in degrees (min, max).
      - `direction_range`: tuple of float, range for the motion bias, should be between -1 and 1 (min, max).
      - `probability`: float, probability of applying the MotionBlur filter.
  - `AtmosphericEffectsFilters`: dict, parameters for the atmospheric effects and miscellaneous filters to apply to the final images and the probability of applying them.
    - [`PlasmaShadow`](https://explore.albumentations.ai/transform/PlasmaShadow): dict, parameters for the PlasmaShadow filter and probability of applying it.
      - `shadow_intensity_range`: tuple of float, range of values for the shadow intensity, should be between 0 and 1 (min, max).
      - `plasma_size`: int, size of the initial plasma pattern grid.
      - `roughness`: float, controls how quickly the plasma noise amplitude increases, should be greater than 0.
      - `probability`: float, probability of applying the PlasmaShadow filter.
    - [`PlasmaBrightnessContrast`](https://explore.albumentations.ai/transform/PlasmaBrightnessContrast): dict, parameters for the PlasmaBrightnessContrast filter and probability of applying it.
      - `brightness_range`: tuple of float, range of values for the spatial brightness adjustment, should be between -1 and 1 (min, max).
      - `contrast_range`: tuple of float, range of values for the spatial contrast adjustment, should be between -1 and 1 (min, max).
      - `plasma_size`: int, size of the initial plasma pattern grid.
      - `roughness`: float, controls how quickly the plasma noise amplitude increases, should be greater than 0.
      - `probability`: float, probability of applying the PlasmaBrightnessContrast filter.
    - [`RandomSunFlare`](https://explore.albumentations.ai/transform/RandomSunFlare): dict, parameters for the RandomSunFlare filter and probability of applying it.
      - `flare_roi`: tuple of float, region where the sun flare can appear in relative coordinates (x_min, y_min, x_max, y_max), should be in range of 0 and 1.
      - `src_radius`: int, radius of the sun circle in pixels.
      - `src_color`: tuple of int, color of the sun in RGB format.
      - `angle_range`: tuple of float, range of angles for the flare direction, should be in range of 0 and 1 (min, max).
      - `num_flare_circles_range`: tuple of int, range for the number of flare circles to generate (min, max).
      - `method`: str, method to use for generating the sun flare, either "overlay" or "physics_based".
      - `probability`: float, probability of applying the RandomSunFlare filter.
    - [`Illumination`](https://explore.albumentations.ai/transform/Illumination): dict, parameters for the Illumination filter and probability of applying it.
      - `mode`: str, type of illumination pattern to use, either "linear", "corner", or "gaussian".
      - `intensity_range`: tuple of float, range of values for the illumination effect strength, should be between 0.01 and 0.2 (min, max).
      - `effect_type`: str, type of lighting change to apply, either "brighten", "darken", or "both".
      - `angle_range`: tuple of float, range of gradient angles in degrees, only used for "linear" mode (min, max).
      - `center_range`: tuple of float, range for the spotlight position in relative coordinates, only used for "gaussian" mode (min, max).
      - `sigma_range`: tuple of float, range for the spotlight size, only used for "gaussian" mode (min, max).
      - `probability`: float, probability of applying the Illumination filter.
    - [`AtmosphericFog`](https://explore.albumentations.ai/transform/AtmosphericFog): dict, parameters for the AtmosphericFog filter and probability of applying it.
      - `density_range`: tuple of float, range of values for the fog density (min, max).
      - `fog_color`: tuple of int, fog color per channel.
      - `depth_mode`: str, method to use for generating synthetic depth, either "linear", "diagonal", or "radial".
      - `probability`: float, probability of applying the AtmosphericFog filter.


## CLI parameters:
- `config_file`: str, path to the config yaml file to use for the generation,
- `num_images`: int, number of images to generate, this will overwrite the value in the config file if provided.
- `output_dir`: str, path to the directory where the generated images and annotations will be saved, this will overwrite the value in the config file if provided.
- `debug`: int or None, whether to generate debug images for a sample of the generated images and how many (if int, the number of debug images to generate, if None, no debug images will be generated), this will overwrite the value in the config file if provided.
- `debug_dir`: str, path to the directory where the debug images will be saved (inside the output directory), only used if `debug`: is not None, this will overwrite the value in the config file if provided.
- `backgrounds_dir`: str, path to the directory where the background images are located, default is "backgrounds", this will overwrite the value in the config file if provided.
