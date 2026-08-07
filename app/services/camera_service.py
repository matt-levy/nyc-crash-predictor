from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.models.risk import Camera


CAMERAS = [
    Camera(
        id="769a2e94-5bbc-4a03-86a7-39d3a70213f7",
        name="Broadway @ 96 St",
        latitude=40.794668,
        longitude=-73.971788,
        area="Manhattan",
        is_online=True,
        image_url="https://webcams.nyctmc.org/api/cameras/769a2e94-5bbc-4a03-86a7-39d3a70213f7/image",
    )
]
CAMERA_CATALOG_URL = "https://webcams.nyctmc.org/api/cameras"


class CameraNotFoundError(Exception):
    pass


class CameraSnapshotError(Exception):
    pass


class CameraCatalogError(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    content: bytes
    content_type: str


def list_cameras() -> list[Camera]:
    return CAMERAS.copy()


def get_camera(camera_id: str) -> Camera:
    camera = next((camera for camera in CAMERAS if camera.id == camera_id), None)
    if camera is None:
        raise CameraNotFoundError(camera_id)
    return camera


async def fetch_camera_catalog() -> list[Camera]:
    """Fetch current public metadata and retain it for later per-camera lookups."""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(CAMERA_CATALOG_URL)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise CameraCatalogError("NYC DOT camera catalog request timed out") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise CameraCatalogError("NYC DOT camera catalog request failed") from exc
    if not isinstance(payload, list):
        raise CameraCatalogError("NYC DOT camera catalog returned an unexpected response")
    try:
        cameras = [
            Camera(
                id=row["id"], name=row["name"], latitude=row["latitude"],
                longitude=row["longitude"], area=row["area"],
                is_online=row["isOnline"], image_url=row["imageUrl"],
            )
            for row in payload
        ]
    except (KeyError, TypeError, ValidationError) as exc:
        raise CameraCatalogError("NYC DOT camera catalog returned malformed records") from exc
    if not cameras:
        raise CameraCatalogError("NYC DOT camera catalog returned no cameras")
    CAMERAS[:] = cameras
    return cameras.copy()


async def fetch_snapshot(camera: Camera) -> Snapshot:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(camera.image_url)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise CameraSnapshotError("NYC DOT camera request timed out") from exc
    except httpx.HTTPError as exc:
        raise CameraSnapshotError("NYC DOT camera request failed") from exc
    content_type = response.headers.get("content-type", "")
    if not content_type.lower().startswith("image/") or not response.content:
        raise CameraSnapshotError("NYC DOT camera returned an invalid image response")
    return Snapshot(content=response.content, content_type=content_type.split(";", 1)[0])


async def verify_snapshot_available(camera: Camera) -> None:
    """Validate the live URL without retaining the image body."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            async with client.stream("GET", camera.image_url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if not content_type.lower().startswith("image/"):
                    raise CameraSnapshotError("NYC DOT camera returned an invalid image response")
    except httpx.TimeoutException as exc:
        raise CameraSnapshotError("NYC DOT camera request timed out") from exc
    except httpx.HTTPError as exc:
        raise CameraSnapshotError("NYC DOT camera snapshot is unavailable") from exc
