"""Settings. Defaults mirror infra/config.ps1; any value can be overridden by an
environment variable of the same name (the Function reads its app settings this way)."""
import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    aoai: str = _env("AOAI", "aoai-ci-dev-2416")
    storage: str = _env("SA", "stcidev2416")
    doc_intel: str = _env("DI", "di-ci-dev-2416")
    search: str = _env("SRCH", "srch-ci-dev-2416")
    index: str = _env("INDEX", "contracts-v1")

    embed_model: str = _env("EMBED_MODEL", "text-embedding-3-large")
    embed_dims: int = int(_env("EMBED_DIMS", "1024"))          # ADR-0016
    embed_batch: int = int(_env("EMBED_BATCH", "16"))
    # Client-side pacing, kept 10% under the deployment's capacity (infra/03b, ADR-0014)
    embed_tpm: int = int(_env("EMBED_TPM", "180000"))

    chunk_tokens: int = int(_env("CHUNK_TOKENS", "800"))       # ADR-0005
    overlap_tokens: int = int(_env("OVERLAP_TOKENS", "120"))   # 15% of 800

    raw_fs: str = "contracts-raw"
    extracted_fs: str = "contracts-extracted"
    layout_api: str = "2024-11-30"
    search_api: str = "2024-07-01"

    @property
    def extraction_version(self) -> str:
        return f"layout-{self.layout_api}"

    @property
    def aoai_endpoint(self) -> str:
        return f"https://{self.aoai}.openai.azure.com/openai/v1"

    @property
    def di_endpoint(self) -> str:
        return f"https://{self.doc_intel}.cognitiveservices.azure.com"

    @property
    def search_endpoint(self) -> str:
        return f"https://{self.search}.search.windows.net"

    @property
    def dfs_endpoint(self) -> str:
        return f"https://{self.storage}.dfs.core.windows.net"


SETTINGS = Settings()
