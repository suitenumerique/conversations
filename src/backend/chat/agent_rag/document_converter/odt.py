import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO




class OtdToMd:
    """Extract text from open document files.
    """

    def extract(self, content: bytes, **kwargs):
        zip_stream = zipfile.ZipFile(BytesIO(content))
        self.content = ET.fromstring(zip_stream.read("content.xml"))
        self._parse_styles()
        return self.to_markdown()

    def _parse_styles(self):
        """Build a map of style name → {bold, italic} from automatic styles."""
        self.styles = {}
        for style in self.content.iter():
            if style.tag == self.qn('style:style'):
                name = style.get(self.qn('style:name'), '')
                props = {}
                for child in style:
                    if child.tag == self.qn('style:text-properties'):
                        if child.get(self.qn('fo:font-weight')) == 'bold':
                            props['bold'] = True
                        if child.get(self.qn('fo:font-style')) == 'italic':
                            props['italic'] = True
                if props:
                    self.styles[name] = props

    def _find_body(self):
        """Find the office:text element containing the document body."""
        for elem in self.content.iter():
            if elem.tag == self.qn('office:text'):
                return elem
        return self.content

    def to_markdown(self):
        """Converts the document to markdown format."""
        body = self._find_body()
        return self._convert_elements(body).strip()

    def _convert_elements(self, parent, list_level=0):
        """Recursively convert ODT elements to markdown."""
        buff = ""
        for child in parent:
            print("🚀️ ---------- odt.py l:35", child.tag)
            if child.tag == self.qn('text:h'):
                level = int(child.get(self.qn('text:outline-level'), '1'))
                text = self.text_to_string(child).strip()
                if text:
                    buff += "#" * level + " " + text + "\n\n"
            elif child.tag == self.qn('text:p'):
                text = self.text_to_string(child)
                if list_level > 0:
                    indent = "  " * (list_level - 1)
                    buff += indent + "- " + text.strip() + "\n"
                else:
                    buff += text + "\n\n"
            elif child.tag == self.qn('text:list'):
                buff += self._convert_elements(child, list_level + 1)
                if list_level == 0:
                    buff += "\n"
            elif child.tag == self.qn('text:list-item'):
                buff += self._convert_elements(child, list_level)
            elif child.tag == self.qn('table:table'):
                buff += self._convert_table(child)
        return buff

    def _convert_table(self, table_elem):
        """Convert a table:table element to a markdown table."""
        rows = []
        for child in table_elem:
            if child.tag == self.qn('table:table-row'):
                cells = []
                for cell in child:
                    if cell.tag == self.qn('table:table-cell'):
                        cell_parts = []
                        for p in cell:
                            if p.tag == self.qn('text:p'):
                                cell_parts.append(self.text_to_string(p, include_tail=False).strip())
                        cell_text = " ".join(cell_parts)
                        repeat = int(cell.get(self.qn('table:number-columns-repeated'), '1'))
                        repeat = min(repeat, 50)
                        cells.extend([cell_text] * repeat)
                if cells:
                    rows.append(cells)
        if not rows:
            return ""
        col_count = len(rows[0])
        buff = "| " + " | ".join(rows[0]) + " |\n"
        buff += "| " + " | ".join("---" for _ in range(col_count)) + " |\n"
        for row in rows[1:]:
            while len(row) < col_count:
                row.append("")
            buff += "| " + " | ".join(row[:col_count]) + " |\n"
        buff += "\n"
        return buff

    def text_to_string(self, element, include_tail=True):
        buff = ""
        if element.text is not None:
            buff += element.text
        for child in element:
            if child.tag == self.qn('text:tab'):
                buff += "\t"
            elif child.tag == self.qn('text:s'):
                buff += " "
                if child.get(self.qn('text:c')) is not None:
                    buff += " " * (int(child.get(self.qn('text:c'))) - 1)
            elif child.tag == self.qn('text:span'):
                inner = self.text_to_string(child, include_tail=False)
                style_name = child.get(self.qn('text:style-name'), '')
                props = self.styles.get(style_name, {})
                if props.get('italic'):
                    inner = "*" + inner + "*"
                if props.get('bold'):
                    inner = "**" + inner + "**"
                buff += inner
            else:
                buff += self.text_to_string(child, include_tail=False)
            if child.tail is not None:
                buff += child.tail
        if include_tail and element.tail is not None:
            buff += element.tail
        return buff

    def qn(self, namespace):
        """Connect tag prefix to longer namespace"""
        nsmap = {
            'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
            'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
            'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
            'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
            'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
        }
        spl = namespace.split(':')
        return '{{{}}}{}'.format(nsmap[spl[0]], spl[1])
