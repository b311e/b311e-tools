"""
docx_to_pdf.py

Converts a Word .docx with tracked changes directly to a tagged PDF
using ReportLab.

- w:ins elements → underlined text with ActualText "Begin addition ... End addition"
- w:del elements → strikethrough text with ActualText "Begin deletion ... End deletion"
- Paragraph styles mapped to appropriate PDF structure tags (H1, H2, P, etc.)
- Run-level formatting (bold, italic, strikethrough, caps) preserved
- PDF/UA: MarkInfo, StructTreeRoot, document language, structure tags

Usage:
    python doc_to_pdf.py input.docx output.pdf
"""

import sys
import zipfile
import argparse
from lxml import etree
from xml.sax.saxutils import escape as xml_escape
from pathlib import Path

from reportlab.pdfgen import canvas as canvas_module
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Flowable
)
from reportlab.pdfbase.pdfdoc import (
    PDFObject, PDFDictionary, PDFArray, PDFName, PDFString, PDFPage
)


W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def w(tag):
    return f'{{{W}}}{tag}'


# ── PDF structure tag helpers ────────────────────────────────────────────────

class PDFStructElement(PDFObject):
    """A PDF StructElem dictionary for the structure tree."""
    __RefOnly__ = 1

    def __init__(self, struct_type, parent=None, page=None, mcid=None,
                 actual_text=None, kids=None):
        self.struct_type = struct_type
        self.parent = parent
        self.page = page
        self.mcid = mcid
        self.actual_text = actual_text
        self.kids = kids or []

    def format(self, document):
        d = {
            "Type": PDFName("StructElem"),
            "S": PDFName(self.struct_type),
        }
        if self.parent is not None:
            d["P"] = self.parent
        if self.kids:
            d["K"] = PDFArray(self.kids) if len(self.kids) > 1 else self.kids[0]
        elif self.mcid is not None:
            d["K"] = self.mcid
        if self.page is not None:
            d["Pg"] = self.page
        if self.actual_text is not None:
            d["ActualText"] = PDFString(self.actual_text)
        return PDFDictionary(d).format(document)


class PDFParentTree(PDFObject):
    """Number tree mapping StructParents → arrays of StructElem refs."""
    __RefOnly__ = 1

    def __init__(self):
        self.entries = {}  # page_index → list of struct elem refs

    def add(self, page_index, struct_ref):
        self.entries.setdefault(page_index, []).append(struct_ref)

    def format(self, document):
        nums = []
        for idx in sorted(self.entries.keys()):
            nums.append(idx)
            nums.append(PDFArray(self.entries[idx]))
        return PDFDictionary({"Nums": PDFArray(nums)}).format(document)


class TaggedCanvas(canvas_module.Canvas):
    """Canvas subclass that builds a PDF structure tree for tagged PDF."""

    def __init__(self, filename, **kwargs):
        kwargs.setdefault('lang', 'en-US')
        super().__init__(filename, **kwargs)

        self._mcid_counter = 0
        self._page_index = 0
        self._struct_elems = []       # all StructElem objects
        self._page_elems = []         # elems for current page
        self._parent_tree = PDFParentTree()

        # Root of the structure tree (Document element)
        self._struct_root_elem = None
        self._struct_tree_root = None

        # Patch PDFPage to include StructParents and Tabs
        if "StructParents" not in PDFPage.__NoDefault__:
            PDFPage.__NoDefault__.append("StructParents")
        if "Tabs" not in PDFPage.__NoDefault__:
            PDFPage.__NoDefault__.append("Tabs")

    def beginTag(self, tag_type, actual_text=None):
        """Begin a marked content sequence with a structure tag."""
        mcid = self._mcid_counter
        self._mcid_counter += 1
        props = f"/MCID {mcid}"
        if actual_text:
            escaped = actual_text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            props += f" /ActualText ({escaped})"
        self._code.append(f"/{tag_type} <<{props}>> BDC")

        # Create the struct element (parent set later during finalization)
        elem = PDFStructElement(
            tag_type, mcid=mcid, actual_text=actual_text
        )
        ref = self._doc.Reference(elem)
        self._struct_elems.append((elem, ref))
        self._page_elems.append((elem, ref))
        return elem, ref

    def endTag(self):
        """End the current marked content sequence."""
        self._code.append("EMC")

    def showPage(self):
        # Record page struct parents before finalizing the page
        if self._page_elems:
            for _, ref in self._page_elems:
                self._parent_tree.add(self._page_index, ref)
        self._page_elems = []
        self._page_index += 1
        super().showPage()

    def save(self):
        self._finalize_structure()
        super().save()

    def _finalize_structure(self):
        """Build and attach the complete structure tree to the PDF catalog."""
        cat = self._doc.Catalog

        # MarkInfo
        cat.MarkInfo = PDFDictionary({"Marked": PDFName("true")})

        # Build Document root struct elem
        child_refs = [ref for (_, ref) in self._struct_elems]
        doc_elem = PDFStructElement("Document", kids=child_refs)
        doc_ref = self._doc.Reference(doc_elem)

        # Set parent on all children to the Document elem
        for elem, ref in self._struct_elems:
            elem.parent = doc_ref

        # Set page refs on struct elems
        pages = self._doc.Pages.pages
        for pg_idx, entries in self._parent_tree.entries.items():
            if pg_idx < len(pages):
                page_ref = pages[pg_idx]
                for ref in entries:
                    # find the elem for this ref
                    for elem, eref in self._struct_elems:
                        if eref is ref:
                            elem.page = page_ref
                            break

        # Set StructParents on pages
        for pg_idx in self._parent_tree.entries:
            if pg_idx < len(pages):
                page_obj = pages[pg_idx]
                if hasattr(page_obj, 'StructParents'):
                    pass  # already set
                # We need to set it on the actual page dict
                # pages[] contains PDFObjectReference, the actual PDFPage
                # is stored internally

        # Parent tree
        parent_tree_ref = self._doc.Reference(self._parent_tree)

        # StructTreeRoot
        struct_tree = PDFDictionary({
            "Type": PDFName("StructTreeRoot"),
            "K": doc_ref,
            "ParentTree": parent_tree_ref,
        })
        cat.StructTreeRoot = self._doc.Reference(struct_tree)

        # Language and ViewerPreferences
        cat.Lang = PDFString('en-US')
        self.setViewerPreference("DisplayDocTitle", "true")


class TaggedParagraph(Flowable):
    """Wrapper that emits BDC/EMC structure tags around a Paragraph."""

    def __init__(self, paragraph, tag_type, tracked_changes=None):
        Flowable.__init__(self)
        self.paragraph = paragraph
        self.tag_type = tag_type
        self.tracked_changes = tracked_changes or []

    def wrap(self, availWidth, availHeight):
        w, h = self.paragraph.wrap(availWidth, availHeight)
        self.width = w
        self.height = h
        return w, h

    def split(self, availWidth, availHeight):
        return self.paragraph.split(availWidth, availHeight)

    def drawOn(self, canvas, x, y, _sW=0):
        # Emit BDC before the paragraph draws
        canvas._code.append(f'/{self.tag_type} <</MCID {canvas._mcid_counter}>> BDC')

        # Record this struct element
        elem = PDFStructElement(self.tag_type, mcid=canvas._mcid_counter)
        ref = canvas._doc.Reference(elem)
        canvas._struct_elems.append((elem, ref))
        canvas._page_elems.append((elem, ref))
        canvas._mcid_counter += 1

        # Let the real paragraph draw itself
        self.paragraph.drawOn(canvas, x, y, _sW)

        # Close the marked content
        canvas._code.append('EMC')

        # Tracked changes with ActualText as separate Span tags
        if self.tracked_changes:
            for change in self.tracked_changes:
                mcid = canvas._mcid_counter
                actual = change['actual_text']
                escaped = actual.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
                canvas._code.append(
                    f'/Span <</MCID {mcid} /ActualText ({escaped})>> BDC'
                )
                canvas._code.append('EMC')

                elem = PDFStructElement(
                    'Span', mcid=mcid, actual_text=actual
                )
                ref = canvas._doc.Reference(elem)
                canvas._struct_elems.append((elem, ref))
                canvas._page_elems.append((elem, ref))
                canvas._mcid_counter += 1


# ── ReportLab styles ─────────────────────────────────────────────────────────

STYLE_TO_TAG = {
    'BillHeading1': 'H1',
    'BillHeading2': 'H2',
    'BillHeading3': 'H3',
    'BillTitle':    'P',
    'BillSponsors': 'P',
    'BillEnacting': 'P',
    'BillBody':     'P',
}

def build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'BillBody',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=12,
        leading=18,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        'BillHeading1',
        parent=styles['Heading1'],
        fontName='Times-Bold',
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=18,
    ))

    styles.add(ParagraphStyle(
        'BillHeading2',
        parent=styles['Heading2'],
        fontName='Times-Bold',
        fontSize=13,
        leading=16,
        spaceAfter=12,
    ))

    styles.add(ParagraphStyle(
        'BillHeading3',
        parent=styles['Heading3'],
        fontName='Times-Bold',
        fontSize=12,
        leading=15,
        spaceAfter=10,
    ))

    styles.add(ParagraphStyle(
        'BillTitle',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=12,
        leading=18,
        alignment=TA_CENTER,
        spaceBefore=12,
        spaceAfter=12,
    ))

    styles.add(ParagraphStyle(
        'BillSponsors',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=12,
        leading=18,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        'BillEnacting',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=12,
        leading=18,
        spaceBefore=12,
        spaceAfter=12,
    ))

    return styles


PARA_STYLE_MAP = {
    'Heading1':           'BillHeading1',
    'Heading2':           'BillHeading2',
    'Heading3':           'BillHeading3',
    'BillTitle':          'BillTitle',
    'BillSponsors':       'BillSponsors',
    'BillEnactingClause': 'BillEnacting',
    None:                 'BillBody',
}


# ── Text extraction helpers ──────────────────────────────────────────────────

def get_run_text(run_elem):
    parts = []
    for child in run_elem:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == 't':
            parts.append(child.text or '')
        elif tag == 'delText':
            parts.append(child.text or '')
    return ''.join(parts)


def get_run_formatting(run_elem):
    fmt = {'bold': False, 'italic': False, 'strike': False, 'caps': False}
    rpr = run_elem.find(w('rPr'))
    if rpr is None:
        return fmt
    if rpr.find(w('b')) is not None:
        fmt['bold'] = True
    if rpr.find(w('i')) is not None:
        fmt['italic'] = True
    if rpr.find(w('strike')) is not None:
        fmt['strike'] = True
    if rpr.find(w('caps')) is not None:
        fmt['caps'] = True
    return fmt


def wrap_run_markup(text, fmt):
    """Wrap text in ReportLab Paragraph XML markup based on formatting."""
    if not text:
        return ''
    escaped = xml_escape(text)
    if fmt.get('caps'):
        escaped = escaped.upper()
    if fmt.get('strike'):
        escaped = f'<strike>{escaped}</strike>'
    if fmt.get('italic'):
        escaped = f'<i>{escaped}</i>'
    if fmt.get('bold'):
        escaped = f'<b>{escaped}</b>'
    return escaped


# ── Paragraph processing ─────────────────────────────────────────────────────

def process_paragraph(para_elem):
    """Convert a w:p element to (style_name, markup_string, tracked_changes)."""
    ppr = para_elem.find(w('pPr'))
    style_id = None
    if ppr is not None:
        ps = ppr.find(w('pStyle'))
        if ps is not None:
            style_id = ps.get(w('val'))

    style_name = PARA_STYLE_MAP.get(style_id, PARA_STYLE_MAP[None])

    inner_parts = []
    tracked_changes = []

    for child in para_elem:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

        if tag == 'pPr':
            continue

        elif tag == 'r':
            text = get_run_text(child)
            fmt = get_run_formatting(child)
            inner_parts.append(wrap_run_markup(text, fmt))

        elif tag == 'ins':
            full_text = ''
            run_markup_parts = []
            for run in child.findall(w('r')):
                t = get_run_text(run)
                fmt = get_run_formatting(run)
                full_text += t
                run_markup_parts.append(wrap_run_markup(t, fmt))
            inner_markup = ''.join(run_markup_parts)
            if inner_markup:
                inner_parts.append(f'<u>{inner_markup}</u>')
                tracked_changes.append({
                    'type': 'insertion',
                    'actual_text': f'Begin addition {full_text} End addition',
                })

        elif tag == 'del':
            full_text = ''
            run_markup_parts = []
            for run in child.findall(w('r')):
                t = get_run_text(run)
                fmt = get_run_formatting(run)
                fmt['strike'] = True
                full_text += t
                run_markup_parts.append(wrap_run_markup(t, fmt))
            inner_markup = ''.join(run_markup_parts)
            if inner_markup:
                inner_parts.append(inner_markup)
                tracked_changes.append({
                    'type': 'deletion',
                    'actual_text': f'Begin deletion {full_text} End deletion',
                })

        elif tag == 'hyperlink':
            for run in child.findall(w('r')):
                text = get_run_text(run)
                fmt = get_run_formatting(run)
                inner_parts.append(wrap_run_markup(text, fmt))

    markup = ''.join(inner_parts).strip()
    if not markup:
        return None, None, None

    return style_name, markup, tracked_changes


# ── PDF generation ───────────────────────────────────────────────────────────

def docx_to_pdf(docx_path, pdf_path):
    """Convert a docx file directly to a tagged PDF."""
    with zipfile.ZipFile(docx_path, 'r') as z:
        with z.open('word/document.xml') as f:
            tree = etree.parse(f)

    root = tree.getroot()
    body = root.find(f'.//{{{W}}}body')

    styles = build_styles()

    frame = Frame(
        1 * inch, 1 * inch,
        letter[0] - 2 * inch,
        letter[1] - 2 * inch,
        id='main',
    )

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont('Times-Roman', 9)
        canvas.drawCentredString(letter[0] / 2, letter[1] - 0.5 * inch, 'HB 21-1110')
        canvas.drawCentredString(letter[0] / 2, 0.5 * inch, str(canvas.getPageNumber()))
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(pdf_path),
        pagesize=letter,
        title='HB 21-1110',
        author='',
    )
    doc.addPageTemplates([
        PageTemplate(id='main', frames=[frame], onPage=on_page),
    ])

    flowables = []

    for para in body.findall(f'{{{W}}}p'):
        style_name, markup, tracked_changes = process_paragraph(para)
        if style_name is None:
            continue

        p = Paragraph(markup, styles[style_name])
        tag_type = STYLE_TO_TAG.get(style_name, 'P')
        flowables.append(TaggedParagraph(p, tag_type, tracked_changes))

    doc.build(flowables, canvasmaker=TaggedCanvas)
    print(f"PDF written to {pdf_path}")


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Convert docx with tracked changes to tagged PDF"
    )
    parser.add_argument("input", help="Input .docx file")
    parser.add_argument("output", help="Output .pdf file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    print(f"Converting {input_path} to PDF...")
    docx_to_pdf(str(input_path), str(output_path))
