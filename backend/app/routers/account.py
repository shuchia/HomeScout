"""Account deletion — the user's own, from Settings.

Required by App Store guideline 5.1.1(v): an app that lets people create an
account must let them delete it in the app, not by emailing us.

What "deleted" means here:
- Files first: every photo, thumbnail and voice recording the user uploaded,
  all under ``tours/{user_id}/`` in the tours bucket. Done before the account
  so a failure leaves the account in place and the user can simply retry —
  the reverse order would orphan files we could no longer attribute to anyone.
- Then the Supabase auth user. Every user table (profiles, saved_listings,
  tour_notes, tour_photos, tour_tags, saved_searches, user_locations,
  notifications, invite_redemptions, beta_feedback) references auth.users
  ``on delete cascade``, so one call removes all of it. analytics_events is
  ``on delete set null``: events stay, unattributed — as the privacy policy says.
- The waitlist is keyed on email, not on the account, and is left alone.
"""
import logging
import re

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import get_current_user, UserContext
from app.services.analytics_service import AnalyticsService
from app.services.storage.photo_service import S3_BUCKET, _get_s3_client
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter()

# A user_id is interpolated into an S3 prefix; anything but a UUID could widen
# "tours/{user_id}/" to other people's files.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _known_file_keys(user_id: str) -> set[str]:
    """Keys the database still points at."""
    keys: set[str] = set()
    photos = supabase_admin.table("tour_photos").select("s3_key, thumbnail_s3_key").eq("user_id", user_id).execute()
    for row in photos.data or []:
        keys.update(k for k in (row.get("s3_key"), row.get("thumbnail_s3_key")) if k)
    notes = supabase_admin.table("tour_notes").select("audio_s3_key").eq("user_id", user_id).execute()
    keys.update(row["audio_s3_key"] for row in notes.data or [] if row.get("audio_s3_key"))
    return keys


def _swept_file_keys(s3, user_id: str) -> set[str]:
    """Everything under the user's prefix, including files no row points at any
    more (a deleted note used to leave its recording behind).

    Needs s3:ListBucket on the tours/ prefix. Without it this logs and returns
    nothing rather than blocking deletion — the known keys still go.
    """
    keys: set[str] = set()
    try:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=f"tours/{user_id}/"):
            keys.update(obj["Key"] for obj in page.get("Contents", []))
    except ClientError as e:
        logger.warning("Account deletion: couldn't list tours/%s/ (%s); deleting known keys only",
                       user_id, e.response.get("Error", {}).get("Code"))
    return keys


def _delete_files(user_id: str) -> int:
    s3 = _get_s3_client()
    keys = sorted(_known_file_keys(user_id) | _swept_file_keys(s3, user_id))
    for i in range(0, len(keys), 1000):  # delete_objects takes at most 1000
        batch = keys[i:i + 1000]
        result = s3.delete_objects(
            Bucket=S3_BUCKET,
            Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
        )
        if result.get("Errors"):
            raise RuntimeError(f"{len(result['Errors'])} of {len(batch)} files not deleted, "
                               f"first: {result['Errors'][0].get('Code')}")
    return len(keys)


@router.delete("/api/account", status_code=204)
async def delete_account(user: UserContext = Depends(get_current_user)):
    """Permanently delete the signed-in user's account, data and files."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    if not _UUID.match(user.user_id or ""):
        raise HTTPException(status_code=400, detail="Unexpected account id")

    try:
        files = _delete_files(user.user_id)
    except Exception as e:
        logger.error("Account deletion: file cleanup failed for %s: %s", user.user_id, e)
        raise HTTPException(status_code=500, detail="Couldn't delete your files. Your account is still there; please try again.")

    try:
        supabase_admin.auth.admin.delete_user(user.user_id)
    except Exception as e:
        logger.error("Account deletion: auth delete failed for %s after %d files: %s", user.user_id, files, e)
        raise HTTPException(status_code=500, detail="Couldn't delete your account. Please try again.")

    logger.info("Account deleted: %s (%d files)", user.user_id, files)
    # No user_id: the account it would point at no longer exists.
    await AnalyticsService.log_event("account-deleted", metadata={"files": files})
    return Response(status_code=204)
