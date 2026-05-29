from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import mimetypes


class MediaExtractor:
    def __init__(self, pptx_path: str | Path, output_dir: str | Path = "outputs/assets") -> None:
        self.pptx_path = Path(pptx_path).expanduser().resolve()
        self.output_dir = Path(output_dir).expanduser()
        if not self.output_dir.is_absolute():
            self.output_dir = Path.cwd() / self.output_dir

    def extract(self) -> list[dict]:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        assets = []
        with ZipFile(self.pptx_path) as package:
            media_paths = sorted(
                [
                    name
                    for name in package.namelist()
                    if name.startswith("ppt/media/")
                    and not name.endswith("/")
                ]
            )

            for media_path in media_paths:
                file_name = Path(media_path).name
                output_path = self.output_dir / file_name
                data = package.read(media_path)
                output_path.write_bytes(data)

                content_type, _ = mimetypes.guess_type(file_name)
                assets.append(
                    {
                        "pptxPath": media_path,
                        "fileName": file_name,
                        "contentType": content_type,
                        "sizeBytes": len(data),
                        "outputPath": str(output_path),
                    }
                )

        return assets
