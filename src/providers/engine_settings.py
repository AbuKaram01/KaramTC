# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The user's OCR engine choices, as one value.

Both tabs build OcrOptions from the same saved OCR Settings; this module is the one place that knows how those
settings map onto OcrOptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from providers import tessdata_manager
from providers.ocr_types import DEFAULT_OEM, DEFAULT_PSM, TESSERACT_TOGGLE_VARIABLES, OcrOptions

# Value of OcrEngineSettings.lang_source that selects the language data installed with Tesseract itself.
SYSTEM_LANG_SOURCE = "system"
# Name of the one numeric Tesseract variable (all the others are on/off toggles).
EDGES_VARIABLE = "edges_max_children_per_outline"


@dataclass
class OcrEngineSettings:
    """The OCR Settings the user saved, in the form both tabs share.

    Attributes:
        oem: Tesseract engine mode.
        psm: Tesseract page segmentation mode.
        preserve_interword_spaces: Keep the spacing between words as it appears on the page.
        custom_params: Raw "key=value; key2=value2" Tesseract variables.
        lang_source: SYSTEM_LANG_SOURCE, or a tessdata_manager quality tier.
        extra_variables: Toggle variables (names in TESSERACT_TOGGLE_VARIABLES mapped to bool) plus, only when
            enabled, EDGES_VARIABLE mapped to int. Saved with a PDF job as "tess_extra".
    """

    oem: int = DEFAULT_OEM
    psm: int = DEFAULT_PSM
    preserve_interword_spaces: bool = False
    custom_params: str = ""
    lang_source: str = SYSTEM_LANG_SOURCE
    extra_variables: dict = field(default_factory=dict)

    def to_ocr_options(
        self, want_pdf: bool = False, want_confidence: bool = True, threads: int | None = None,
    ) -> OcrOptions:
        """Build the OcrOptions for one job from these settings.

        Args:
            want_pdf: Also produce a searchable PDF.
            want_confidence: Also compute the mean confidence.
            threads: CPU threads the engine may use; None leaves the choice to the engine.
        """
        tessdata_dir = (
            None if self.lang_source == SYSTEM_LANG_SOURCE
            else tessdata_manager.local_tessdata_dir(self.lang_source)
        )
        toggles = {name: self.extra_variables.get(name, False) for name in TESSERACT_TOGGLE_VARIABLES}
        return OcrOptions(
            oem=self.oem,
            psm=self.psm,
            preserve_interword_spaces=self.preserve_interword_spaces,
            edges_max_children_per_outline=self.extra_variables.get(EDGES_VARIABLE),
            custom_params=self.custom_params,
            tessdata_dir=tessdata_dir,
            want_pdf=want_pdf,
            want_confidence=want_confidence,
            threads=threads,
            **toggles,
        )
