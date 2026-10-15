from pydantic import BaseModel


class BuildRequest(BaseModel):
    keystore: str = "test"  # "test" uses the generated lab signing key


class ComparisonOut(BaseModel):
    expected_differences: list[str]
    important_differences: list[str]
    summary: dict
    compatible: bool
