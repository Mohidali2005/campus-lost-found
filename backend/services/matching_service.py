# backend/services/matching_service.py
# ─────────────────────────────────────────────────────────────────────────────
# CLIP-based image/text matching service for Phase 7.
#
# What is CLIP?
#   CLIP (Contrastive Language-Image Pretraining) is an AI model from OpenAI
#   that can convert images OR text into a shared "embedding space" — a list of
#   512 numbers (a vector) that captures the meaning of what's in the image or
#   text. Items that look or sound similar will have similar vectors.
#
# How matching works:
#   1. When a new item is posted, we encode it into a 512-dim vector and save
#      it to Item.embedding (JSON text in the database).
#   2. We then compare that vector against all items of the OPPOSITE type
#      (lost ↔ found) that already have embeddings.
#   3. If two items are similar enough (cosine similarity >= clip_threshold),
#      we save a Match record in the matches table.
#   4. Phase 8 (dashboard) will surface these matches to registered users.
#
# Why lazy loading?
#   The CLIP model is large (~600 MB). We don't want the server to spend
#   30+ seconds downloading it on every startup. Instead we use a lazy pattern:
#   _model and _processor start as None and are loaded on first use.
# ─────────────────────────────────────────────────────────────────────────────

import json       # for encoding/decoding the embedding list to/from a JSON string
import os         # for building file paths on disk
import logging    # for printing info/warning messages without crashing the app

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Item, ItemType, Match

# ── Logging setup ─────────────────────────────────────────────────────────────
# We use Python's built-in logger instead of print() so messages include the
# module name, timestamp, and severity level in server output.
logger = logging.getLogger(__name__)


# ── Lazy model state ──────────────────────────────────────────────────────────
# These module-level variables hold the loaded model and processor.
# They start as None and are set the first time _load_model() is called.
# After that first call, subsequent calls skip the loading step entirely.

_model = None       # the CLIP neural network weights
_processor = None   # converts images/text into the tensor format the model needs
_load_attempted = False  # track if we already tried (and failed) to load


def _load_model() -> bool:
    """
    Lazily loads the CLIP model and processor on first use.

    Returns True if the model loaded successfully, False if torch/transformers
    are not installed or the download failed. Callers should check the return
    value and skip embedding computation gracefully if False.

    Why 'openai/clip-vit-base-patch32'?
      This is the standard CLIP model with a 32-patch ViT image encoder.
      It produces 512-dim vectors — small enough to store in a text column,
      fast enough to run on CPU without a GPU.
    """
    global _model, _processor, _load_attempted

    # If we already loaded successfully, nothing to do
    if _model is not None and _processor is not None:
        return True

    # If we already tried and failed, don't retry on every request
    if _load_attempted:
        return False

    _load_attempted = True

    try:
        # Import here (not at module top) so the server starts even if
        # torch or transformers aren't installed
        from transformers import CLIPModel, CLIPProcessor

        logger.info("Loading CLIP model 'openai/clip-vit-base-patch32' — first-time download may take a minute...")

        # CLIPProcessor handles image resizing/normalizing and text tokenisation
        _processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        # CLIPModel is the actual neural network (image encoder + text encoder)
        _model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")

        # Put model in eval mode — disables dropout and batch norm training behaviour
        _model.eval()

        logger.info("CLIP model loaded successfully.")
        return True

    except Exception as exc:
        # This catches: ImportError (torch not installed), network errors
        # (can't download model), disk errors, etc.
        logger.warning(f"CLIP model could not be loaded — matching disabled. Reason: {exc}")
        return False


# ── Eager startup loader ──────────────────────────────────────────────────────

def preload_model() -> None:
    """
    Public function called at server startup to load CLIP immediately.

    Called from main.py's lifespan hook (before the server accepts any
    requests) so the model is warm before the first user ever posts an item.
    If loading fails the server still starts — matching is just disabled.
    """
    _load_model()


# ── Cosine similarity ─────────────────────────────────────────────────────────

def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Computes cosine similarity between two vectors.

    Cosine similarity measures the angle between two vectors:
      - 1.0 = identical direction (same item)
      - 0.0 = completely unrelated
      - -1.0 = opposite (rare for images)

    IMPORTANT: Both vectors MUST be L2-normalised (length = 1) before calling
    this. When they are, the dot product equals cosine similarity — a much
    faster calculation. We normalise inside encode_image() and encode_text(),
    so the guarantee is always met.

    Why not use numpy? We could, but for 512-dim vectors the overhead of
    importing numpy is not worth it. A manual dot product is fine.
    """
    # dot product: multiply each pair of elements, then sum them all up
    return sum(a * b for a, b in zip(vec_a, vec_b))


# ── Image encoding ────────────────────────────────────────────────────────────

def encode_image(image_path_on_disk: str) -> list[float] | None:
    """
    Encodes an image file into a 512-dim normalised CLIP vector.

    Args:
        image_path_on_disk: absolute or relative path to the image file on disk,
                            e.g. "backend/uploads/uuid.jpg"

    Returns:
        A list of 512 floats if successful, or None if encoding fails
        (model not loaded, file not found, corrupt image, etc.)
    """
    # Load the model if not already loaded; bail if it fails
    if not _load_model():
        return None

    try:
        import torch
        from PIL import Image  # Pillow — reads JPEG/PNG/etc. into a Python image object

        # Open the image and convert to RGB (CLIP expects 3-channel colour images;
        # greyscale or RGBA images need conversion first)
        image = Image.open(image_path_on_disk).convert("RGB")

        # CLIPProcessor resizes the image to 224×224 (what CLIP was trained on),
        # normalises pixel values, and converts to a PyTorch tensor
        inputs = _processor(images=image, return_tensors="pt")

        # Run the image through CLIP's image encoder.
        # torch.no_grad() disables gradient tracking — we're doing inference,
        # not training, so gradients are wasted memory.
        with torch.no_grad():
            # get_image_features() runs only the image encoder half of CLIP,
            # returning a (1, 512) tensor
            image_features = _model.get_image_features(**inputs)

        # L2 normalise: divide each vector by its own length so ||v|| = 1.
        # After this, dot product = cosine similarity.
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # .squeeze(0) removes the batch dimension: shape (1, 512) → (512,)
        # .tolist() converts the PyTorch tensor to a plain Python list of floats
        return image_features.squeeze(0).tolist()

    except Exception as exc:
        logger.warning(f"Failed to encode image '{image_path_on_disk}': {exc}")
        return None


# ── Text encoding ─────────────────────────────────────────────────────────────

def encode_text(text: str) -> list[float] | None:
    """
    Encodes a text string into a 512-dim normalised CLIP vector.

    Used as a fallback when an item has no photo — we embed the title +
    description instead so text-only items can still be matched.

    The CLIP text encoder shares the same embedding space as the image encoder,
    so a text embedding like "blue HP laptop" will be close to an image embedding
    of an actual blue HP laptop. This is the magic of CLIP.
    """
    if not _load_model():
        return None

    try:
        import torch

        # CLIPProcessor tokenises the text (splits into word-pieces, adds special
        # tokens, pads to the right length).
        # padding=True and truncation=True handle very long or very short inputs.
        inputs = _processor(
            text=[text],           # must be a list (processor expects a batch)
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=77,         # CLIP's text encoder has a 77-token limit
        )

        with torch.no_grad():
            # get_text_features() runs the text encoder half of CLIP,
            # returning a (1, 512) tensor
            text_features = _model.get_text_features(**inputs)

        # L2 normalise — same as for images
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        return text_features.squeeze(0).tolist()

    except Exception as exc:
        logger.warning(f"Failed to encode text: {exc}")
        return None


# ── Compute and store embedding for an item ───────────────────────────────────

def compute_and_store_embedding(item: Item, db: Session) -> None:
    """
    Computes a CLIP embedding for a newly posted item and saves it to the DB.

    Strategy:
      - If the item has a photo → encode the image (more accurate)
      - If no photo → encode the title + description as text (fallback)

    The embedding is stored as a JSON string in Item.embedding, e.g.:
      "[0.123, -0.456, 0.789, ...]"   (512 floats)

    If embedding fails for any reason, we log a warning and leave
    Item.embedding as None — the item is still posted successfully.
    The item just won't participate in AI matching.
    """
    embedding: list[float] | None = None

    if item.image_path:
        # image_path is like "/uploads/uuid.jpg" — a URL path, not a disk path.
        # Extract just the filename and build the real path on disk.
        filename = os.path.basename(item.image_path)  # "uuid.jpg"
        disk_path = os.path.join(settings.upload_dir, filename)  # "backend/uploads/uuid.jpg"

        logger.info(f"Computing image embedding for item {item.id} from '{disk_path}'")
        embedding = encode_image(disk_path)

    else:
        # No photo — fall back to encoding the text description
        text_to_encode = f"{item.title} {item.description}"
        logger.info(f"Computing text embedding for item {item.id} (no photo)")
        embedding = encode_text(text_to_encode)

    if embedding is not None:
        # Store the list as a JSON string — SQLite has no native array type
        item.embedding = json.dumps(embedding)
        db.add(item)
        db.commit()
        logger.info(f"Embedding saved for item {item.id} (dim={len(embedding)})")
    else:
        logger.warning(f"Could not compute embedding for item {item.id} — skipping.")


# ── Find and save matches ─────────────────────────────────────────────────────

def find_and_save_matches(new_item: Item, db: Session) -> None:
    """
    Compares a newly posted item's embedding against all existing items of the
    OPPOSITE type and saves high-similarity pairs to the matches table.

    Logic:
      - new_item is "lost"  → compare against all "found" items
      - new_item is "found" → compare against all "lost" items
      - Only compare items that already have an embedding stored
      - If cosine_similarity >= settings.clip_threshold (default 0.70), create a Match
      - Skip if a Match record for that (lost_id, found_id) pair already exists
        to avoid duplicate rows on re-matching

    Args:
        new_item: The Item ORM object that was just created (must already have
                  embedding set — call compute_and_store_embedding() first)
        db:       The SQLAlchemy database session
    """
    # No embedding means no matching is possible
    if new_item.embedding is None:
        logger.info(f"Item {new_item.id} has no embedding — skipping match search.")
        return

    # Decode our item's embedding from JSON string back to a Python list
    new_vec: list[float] = json.loads(new_item.embedding)

    # Determine which type to match AGAINST.
    # A lost item should match against found items, and vice versa.
    if new_item.type == ItemType.lost:
        opposite_type = ItemType.found
    else:
        opposite_type = ItemType.lost

    logger.info(f"Searching for {opposite_type.value} items to match against item {new_item.id}...")

    # Fetch all opposite-type items that have an embedding.
    # embedding.isnot(None) = WHERE embedding IS NOT NULL in SQL.
    # We exclude the new item itself (shouldn't be needed since type differs,
    # but it's a good defensive check).
    candidates = (
        db.query(Item)
        .filter(
            Item.type == opposite_type,
            Item.embedding.isnot(None),
            Item.id != new_item.id,
        )
        .all()
    )

    logger.info(f"Found {len(candidates)} candidate(s) to compare.")

    new_matches = 0

    for candidate in candidates:
        # Decode the candidate's embedding
        candidate_vec: list[float] = json.loads(candidate.embedding)

        # Compute cosine similarity (both vectors are already L2-normalised)
        score = _cosine_similarity(new_vec, candidate_vec)

        # Only create a Match if the score meets the threshold
        if score < settings.clip_threshold:
            continue

        # ── Determine lost_item_id and found_item_id ──────────────────────────
        # The Match table always stores lost_item_id and found_item_id explicitly
        # so it's clear which is which, regardless of which was posted first.
        if new_item.type == ItemType.lost:
            lost_id  = new_item.id
            found_id = candidate.id
        else:
            lost_id  = candidate.id
            found_id = new_item.id

        # ── Avoid duplicate Match records ─────────────────────────────────────
        # If both items were posted close together, or if matching is re-run,
        # we don't want to insert the same (lost_id, found_id) pair twice.
        already_exists = (
            db.query(Match)
            .filter(
                Match.lost_item_id == lost_id,
                Match.found_item_id == found_id,
            )
            .first()
        )

        if already_exists:
            continue

        # ── Save the Match record ─────────────────────────────────────────────
        match = Match(
            lost_item_id=lost_id,
            found_item_id=found_id,
            similarity_score=round(score, 4),  # store 4 decimal places (e.g. 0.8731)
        )
        db.add(match)
        new_matches += 1
        logger.info(
            f"  Match: lost#{lost_id} ↔ found#{found_id} "
            f"score={score:.4f} (threshold={settings.clip_threshold})"
        )

    if new_matches > 0:
        db.commit()  # save all new Match rows in one transaction

    logger.info(f"Matching complete for item {new_item.id}: {new_matches} new match(es) saved.")
