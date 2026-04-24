"""Multi-layer guardrail system for the DCS NSW Government chatbot."""

from guardrails.base import GuardRail, GuardRailResult, OutputGuardRailBase
from guardrails.constants import ALL_BLOCK_MESSAGES, SECURITY_BLOCK_MESSAGES
from guardrails.regex_utils import redact_secrets

from guardrails.input import (
    InputLengthGuardRail,
    SecretsInputGuardRail,
    DateTimeInjectorGuardRail,
    BanWordsInputGuardRail,
    JailbreakGuardRail,
    CrisisDetectionInputGuardRail,
    ImproperContentGuardRail,
    CompositeInputJudgeGuardRail,
)
from guardrails.output import (
    OutputLengthGuardRail,
    CreditCardRedactionGuardRail,
    SecretsOutputGuardRail,
    JailbreakOutputGuardRail,
    DlpOutputGuardRail,
    ContentModerationOutputGuardRail,
    BanWordsGuardRail,
    CitizenReadabilityOutputGuardRail,
    LanguageCheckGuardRail,
    CompositeOutputJudgeGuardRail,
    NSWAIComplianceGuardRail,
    RequiredInclusionsGuardRail,
    InformationCurrencyGuardRail,
)
from guardrails.tool import ToolCallGuardRail, ToolResponseGuardRail
from guardrails.post_process import (
    GroundednessChecker,
    RelevancyChecker,
    CopyrightComplianceChecker,
)

__all__ = [
    # Base types
    "GuardRail", "GuardRailResult", "OutputGuardRailBase",
    # Constants
    "ALL_BLOCK_MESSAGES", "SECURITY_BLOCK_MESSAGES",
    # Utilities
    "redact_secrets",
    # Input
    "InputLengthGuardRail", "SecretsInputGuardRail", "DateTimeInjectorGuardRail",
    "BanWordsInputGuardRail", "JailbreakGuardRail", "CrisisDetectionInputGuardRail",
    "ImproperContentGuardRail", "CompositeInputJudgeGuardRail",
    # Output
    "OutputLengthGuardRail", "CreditCardRedactionGuardRail", "SecretsOutputGuardRail",
    "JailbreakOutputGuardRail", "DlpOutputGuardRail", "ContentModerationOutputGuardRail",
    "BanWordsGuardRail", "CitizenReadabilityOutputGuardRail", "LanguageCheckGuardRail",
    "CompositeOutputJudgeGuardRail", "NSWAIComplianceGuardRail", "RequiredInclusionsGuardRail",
    "InformationCurrencyGuardRail",
    # Tool
    "ToolCallGuardRail", "ToolResponseGuardRail",
    # Post-process
    "GroundednessChecker", "RelevancyChecker", "CopyrightComplianceChecker",
]
