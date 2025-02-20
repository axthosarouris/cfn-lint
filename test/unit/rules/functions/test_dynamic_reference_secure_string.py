"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""

import pytest

from cfnlint.context import create_context_for_template
from cfnlint.jsonschema import CfnTemplateValidator, ValidationError
from cfnlint.rules.functions.DynamicReferenceSecureString import (
    DynamicReferenceSecureString,
)
from cfnlint.template import Template


@pytest.fixture(scope="module")
def rule():
    rule = DynamicReferenceSecureString()
    yield rule


@pytest.fixture(scope="module")
def cfn():
    return Template(
        "",
        {
            "Resources": {
                "MyResource": {
                    "Type": "AWS::IAM::User",
                    "Properties": {"LoginProfile": {"Password": "Foo"}},
                }
            }
        },
        regions=["us-east-1"],
    )


@pytest.fixture(scope="module")
def context(cfn):
    return create_context_for_template(cfn)


@pytest.mark.parametrize(
    "name,instance,path,expected",
    [
        (
            "Valid SSM Secure Parameter",
            "{{resolve:ssm-secure:Parameter}}",
            ["Resources", "MyResource", "Properties", "LoginProfile", "Password"],
            [],
        ),
        (
            "Invalid SSM secure location",
            "{{resolve:ssm-secure:Parameter}}",
            ["Outputs", "MyOutput", "Value"],
            [
                ValidationError(
                    (
                        "Dynamic reference '{{resolve:ssm-secure:Parameter}}' "
                        "to SSM secure strings can only be used in resource properties"
                    ),
                    rule=DynamicReferenceSecureString(),
                )
            ],
        ),
    ],
)
def test_validate(name, instance, path, expected, rule, context, cfn):
    for p in path:
        context = context.evolve(path=p)
    validator = CfnTemplateValidator(context=context, cfn=cfn)
    errs = list(rule.validate(validator, {"type": "string"}, instance, {}))
    assert errs == expected, f"Test {name!r} got {errs!r}"
