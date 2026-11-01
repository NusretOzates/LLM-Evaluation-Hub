"""Dataset import adapter for the capability-free Python runtime."""

from pydantic import ValidationError

from llm_evaluation_hub.core.datasets.records import ProcessedExample
from llm_evaluation_hub.execution.python import (
    ProcessorError,
    PythonRunner,
    _field_path,
    validate_json_budget,
)


class ProcessorRunner(PythonRunner):
    """Validate processor output as a dataset example."""

    def process(self, row: dict[str, object]) -> ProcessedExample | None:
        """Process one source row and enforce the dataset contract."""
        if not isinstance(row, dict):
            raise ProcessorError("input", "Processor input must be a JSON object.")
        output = self.run(row)
        if output is None:
            return None
        if not isinstance(output, dict):
            raise ProcessorError("validation", "Processor must return a dictionary or None.")
        try:
            example = ProcessedExample.model_validate(output)
        except ValidationError as error:
            issue = error.errors(include_input=False, include_context=False, include_url=False)[0]
            raise ProcessorError(
                "validation",
                "Processor output does not match the example contract.",
                field_path=_field_path(issue["loc"]),
            ) from None
        validate_json_budget(example.model_dump(mode="json"), category="validation")
        return example
