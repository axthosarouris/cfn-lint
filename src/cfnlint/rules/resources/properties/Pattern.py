"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""

import regex as re

from cfnlint.jsonschema._keywords import pattern
from cfnlint.rules import CloudFormationLintRule


class Pattern(CloudFormationLintRule):
    """Check if properties have a valid value"""

    id = "E3031"
    shortdesc = "Check if property values adhere to a specific pattern"
    description = (
        "Check if properties have a valid value in case of a pattern (Regular"
        " Expression)"
    )
    source_url = "https://github.com/aws-cloudformation/cfn-lint/blob/main/docs/cfn-schema-specification.md#pattern"
    tags = ["resources", "property", "allowed pattern", "regex"]
    child_rules = {
        "W2031": None,
    }

    def __init__(self):
        """Init"""
        super().__init__()
        self.config_definition = {
            "exceptions": {
                "default": [],
                "type": "list",
                "itemtype": "string",
            }
        }
        self.configure()

    def _is_exception(self, instance: str) -> bool:
        for exception in self.config["exceptions"]:
            if re.match(exception, instance):
                return True
        return False

    # pylint: disable=unused-argument, arguments-renamed
    def pattern(self, validator, patrn, instance, schema):
        if (
            len(validator.context.value_path) > 0
            and validator.context.value_path[0] == "Parameters"
        ):
            if self.child_rules.get("W2031"):
                yield from self.child_rules["W2031"].pattern(
                    validator, patrn, instance, schema
                )
            return
        for err in pattern(validator, patrn, instance, schema):
            if not self._is_exception(instance):
                yield err
