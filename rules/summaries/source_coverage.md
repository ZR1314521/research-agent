# Source Coverage

## Fully extracted public guide pages

- Nature formatting guide: `rules/raw/nature-formatting-guide-full.md`
- IEEE Author Center editorial style page: `rules/raw/ieee-editorial-style-manual-full.md`
- Science information for authors: `rules/raw/science-information-for-authors-full.md`
- Cell information for authors: `rules/raw/cell-information-for-authors-full.md`
- Elsevier policies and guidelines for authors: `rules/raw/elsevier-policies-guidelines-full.md`
- ACM citation style and reference formats: `rules/raw/acm-reference-formatting-full.md`
- PNAS manuscript submission guidance: `rules/raw/pnas-submit-manuscript-full.md`

## CSL styles downloaded

See `rules/reference_styles/download_manifest.json` and `rules/reference_styles/download_manifest_extra.json`.

Downloaded profiles include GB/T 7714 numeric and author-date, IEEE, Nature, Science, Cell, Elsevier Vancouver, Elsevier Harvard, Springer Vancouver, ACM, ACS, AMA, BMJ, NEJM, APA, Royal Society of Chemistry, Angewandte Chemie, China Information, Acta Physica Sinica, and Chinese Medical Journal.

## Attempted but not used as strong rule sources

- JAMA and NEJM web pages returned wait/anti-bot pages through OpenCLI.
- The sampled Springer URL returned a page-not-found extract.
- ACS page extraction reached a cookie/login shell, but the ACS CSL profile was downloaded.
- Some expected CSL filenames returned 404; failures are recorded in the manifests.

## Compliance note

Full GB/T 7714 standard text is not bundled to avoid copying paid/copyrighted standards. The implementation uses public CSL styles and local rule summaries, and marks uncertain fields in `citation_check_report.md`.
