"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Sequence, Tuple, Union

import cfnlint.helpers
import cfnlint.rules.custom
from cfnlint.match import Match
from cfnlint.template import Template

LOGGER = logging.getLogger(__name__)


def _rule_is_enabled(
    rule: "CloudFormationLintRule",
    include_experimental: bool = False,
    ignore_rules: List[str] | None = None,
    include_rules: List[str] | None = None,
    mandatory_rules: List[str] | None = None,
):
    """Is the rule enabled based on the configuration"""
    ignore_rules = ignore_rules or []
    include_rules = include_rules or []
    mandatory_rules = mandatory_rules or []

    # Evaluate experimental rules
    if rule.experimental and not include_experimental:
        return False

    # Evaluate includes first:
    include_filter = False
    for include_rule in include_rules:
        if rule.id.startswith(include_rule):
            include_filter = True
    if not include_filter:
        return False

    # Enable mandatory rules without checking for if they are ignored
    for mandatory_rule in mandatory_rules:
        if rule.id.startswith(mandatory_rule):
            return True

    # Allowing ignoring of rules based on prefix to ignore checks
    for ignore_rule in ignore_rules:
        if rule.id.startswith(ignore_rule) and ignore_rule:
            return False

    return True


class RuleMatch:
    """Rules Error"""

    def __init__(self, path: Sequence[str | int], message: str, **kwargs):
        """Init"""
        self.path: Sequence[str | int] = path
        self.path_string: str = "/".join(map(str, path))
        self.message: str = message
        self.context: List[RuleMatch] = []
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __eq__(self, item):
        """Override unique"""
        return (self.path, self.message) == (item.path, item.message)

    def __hash__(self):
        """Hash for comparisons"""
        return hash((self.path, self.message))


def _rule_match_to_match(
    rule: CloudFormationLintRule,
    filename: str,
    cfn: Template,
    match: RuleMatch,
    parent_id: str | None = None,
) -> Iterator[Match]:
    error_rule = rule
    if hasattr(match, "rule"):
        error_rule = match.rule
    linenumbers: Union[Tuple[int, int, int, int], None] = None
    if hasattr(match, "location"):
        linenumbers = match.location
    else:
        linenumbers = cfn.get_location_yaml(cfn.template, match.path)
    if linenumbers:
        result = Match.create(
            linenumber=linenumbers[0] + 1,
            columnnumber=linenumbers[1] + 1,
            linenumberend=linenumbers[2] + 1,
            columnnumberend=linenumbers[3] + 1,
            filename=filename,
            rule=error_rule,
            message=match.message,
            rulematch_obj=match,
            parent_id=parent_id,
        )
    else:
        result = Match.create(
            filename=filename,
            rule=error_rule,
            message=match.message,
            rulematch_obj=match,
            parent_id=parent_id,
        )

    yield result

    for sub_match in match.context:
        sub_match.path = list(match.path) + list(sub_match.path)
        yield from _rule_match_to_match(
            rule=rule, filename=filename, cfn=cfn, match=sub_match, parent_id=result.id
        )


def matching(match_type: Any):
    """Does Logging for match functions"""

    def decorator(match_function):
        """The Actual Decorator"""

        def wrapper(self, filename: str, cfn: Template, *args, **kwargs):
            """Wrapper"""
            if not getattr(self, match_type):
                return

            if match_type == "match_resource_properties":
                if args[1] not in self.resource_property_types:
                    return

            start = datetime.now()
            LOGGER.debug("Starting match function for rule %s at %s", self.id, start)
            # pylint: disable=E1102
            for result in match_function(self, filename, cfn, *args, **kwargs):
                yield from _rule_match_to_match(self, filename, cfn, result)

            LOGGER.debug(
                "Complete match function for rule %s at %s.  Ran in %s",
                self.id,
                datetime.now(),
                datetime.now() - start,
            )

        return wrapper

    return decorator


class CloudFormationLintRule:
    """CloudFormation linter rules"""

    id: str = ""
    shortdesc: str = ""
    description: str = ""
    source_url: str = ""
    tags: List[str] = []
    experimental: bool = False

    logger = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.resource_property_types: List[str] = []
        self.resource_sub_property_types: List[str] = []
        self.config: Dict[str, Any] = {}  # `-X E3012:strict=false`... Show more
        self.config_definition: Dict[str, Any] = {}
        self._child_rules: Dict[str, "CloudFormationLintRule"] = {}
        # Parent IDs to do the opposite of child rules
        self._parent_rules: List[str] = []
        super().__init__()

    def __repr__(self):
        return f"{self.id}: {self.shortdesc}"

    @property
    def child_rules(self):
        return self._child_rules

    @child_rules.setter
    def child_rules(self, rules: Dict[str, "CloudFormationLintRule"]):
        self._child_rules = rules

    @property
    def parent_rules(self):
        return self._parent_rules

    @parent_rules.setter
    def parent_rules(self, rules: List[str]):
        self._parent_rules = rules

    @property
    def severity(self):
        """Severity level"""
        levels = {
            "I": "informational",
            "E": "error",
            "W": "warning",
        }
        return levels.get(self.id[0].upper(), "unknown")

    def verbose(self):
        """Verbose output"""
        return f"{self.id}: {self.shortdesc}\n{self.description}"

    def initialize(self, cfn: Template):
        """Initialize the rule"""

    def is_enabled(
        self,
        include_experimental=False,
        ignore_rules=None,
        include_rules=None,
        mandatory_rules=None,
    ):
        return _rule_is_enabled(
            self, include_experimental, ignore_rules, include_rules, mandatory_rules
        )

    def configure(self, configs=None, experimental=False):
        """Set the configuration"""

        # set defaults
        if isinstance(self.config_definition, dict):
            for config_name, config_values in self.config_definition.items():
                self.config[config_name] = config_values["default"]

        # set experimental if the rule is asking for it
        if "experimental" in self.config_definition:
            if self.config_definition["experimental"]["type"] == "boolean":
                self.config["experimental"] = cfnlint.helpers.bool_compare(
                    experimental, True
                )

        if isinstance(configs, dict):
            for key, value in configs.items():
                if key in self.config_definition:
                    if self.config_definition[key]["type"] == "boolean":
                        self.config[key] = cfnlint.helpers.bool_compare(value, True)
                    elif self.config_definition[key]["type"] == "string":
                        self.config[key] = str(value)
                    elif self.config_definition[key]["type"] == "integer":
                        self.config[key] = int(value)
                    elif self.config_definition[key]["type"] == "list":
                        self.config[key] = []
                        for l_value in value:
                            if self.config_definition[key]["itemtype"] == "boolean":
                                self.config[key].append(
                                    cfnlint.helpers.bool_compare(l_value, True)
                                )
                            elif self.config_definition[key]["itemtype"] == "string":
                                self.config[key].append(str(l_value))
                            elif self.config_definition[key]["itemtype"] == "integer":
                                self.config[key].append(int(l_value))

    match: Callable[[Template], List[RuleMatch]] = None  # type: ignore
    # ruff: noqa: E501
    match_resource_properties: Callable[[Dict, str, List[str], Template], List[RuleMatch]] = None  # type: ignore

    @matching("match")
    # pylint: disable=W0613
    def matchall(self, filename: str, cfn: Template):
        """Match the entire file"""
        return self.match(cfn)  # pylint: disable=E1102

    @matching("match_resource_properties")
    # pylint: disable=W0613
    def matchall_resource_properties(
        self, filename, cfn, resource_properties, property_type, path
    ):
        """Check for resource properties type"""
        return self.match_resource_properties(  # pylint: disable=E1102
            resource_properties, property_type, path, cfn
        )
