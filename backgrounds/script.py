import os
import re
import requests
from urllib.parse import unquote

# Configuration
LIMIT = 10  # Number of samples per category to save
BASE_URL = "https://ambientCG.com/api/v3/assets"

# Maps your custom category strings to ambientCG category ids and optional search query
CATEGORIES_MAPPING = {
    "dirt ground": {"category": "Ground", "query": "Dirt"},
    "concrete ground": {"category": "Concrete", "query": None},
    "asphalt ground": {"category": "Asphalt", "query": None},
    "rocky ground": {"category": "Ground", "query": "rock"},
    "flaky paint": {"category": "", "query": "painted"},
    "gravel": {"category": "Gravel", "query": None},
    "grass": {"category": "Grass", "query": None},
    "wood": {"category": "Wood", "query": None},
    "chipboard": {"category": "", "query": "Chipboard"}
    "tiled ground": {"category": "Tiles", "query": None},
}


def _extract_preview_image_url(preview_url: str) -> str | None:
    """Extract a direct color/texture JPG URL from the preview URL fragment/query.

    The preview `url` often encodes direct texture URLs in the fragment as
    `texture_url=...` or `color_url=...` followed by comma-separated map URLs.
    We try to capture the first (color) entry and return it.
    """
    if not preview_url:
        return None

    # look for texture_url= or color_url= and capture the value until next & or end
    m = re.search(r"(?:texture_url|color_url)=([^&]+)", preview_url)
    if not m:
        return None

    value = unquote(m.group(1))
    # the value may be comma-separated list of urls; take first
    first = value.split(",")[0]
    # sanitize
    first = first.strip()
    return first or None


def download_textures():
    for folder_name, config in CATEGORIES_MAPPING.items():
        print(f"\n=== Processing target category: '{folder_name}' ===")

        safe_folder_name = folder_name.replace(" ", "_")
        os.makedirs(safe_folder_name, exist_ok=True)

        # Build parameters using API v3 semantics (lowercase type)
        params = {
            "category": config["category"],
            "type": "material",
            "limit": LIMIT * 2,  # fetch a larger pool to allow filtering
            "include": "previews"
        }

        if config.get("query"):
            params["q"] = config["query"]

        try:
            response = requests.get(BASE_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[-] Network/API error for '{folder_name}': {e}")
            continue

        assets = data.get("assets", [])
        if not assets:
            print(f"[-] No assets returned for '{folder_name}'.")
            continue

        count = 0
        for asset in assets:
            asset_id = asset.get("id") or asset.get("assetId")
            if not asset_id:
                continue

            # try to extract a color/texture image URL from previews
            image_url = None
            previews = asset.get("previews", []) or []
            for p in previews:
                url = p.get("url")
                image_url = _extract_preview_image_url(url)
                if image_url:
                    break

            # nothing found in previews -> skip (could fall back to downloads include)
            if not image_url:
                continue

            file_name = f"{asset_id}.jpg"
            file_path = os.path.join(safe_folder_name, file_name)

            try:
                print(f"[+] Download progress [{count+1}/{LIMIT}]: {asset_id} -> {image_url}")
                img_response = requests.get(image_url, stream=True, timeout=30)
                img_response.raise_for_status()

                with open(file_path, "wb") as f:
                    for chunk in img_response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                count += 1
            except Exception as e:
                print(f"[-] Failed to download {asset_id}: {e}")

            if count >= LIMIT:
                break

        print(f"[✓] Completed: './{safe_folder_name}' updated with {count} textures.")


if __name__ == "__main__":
    download_textures()
