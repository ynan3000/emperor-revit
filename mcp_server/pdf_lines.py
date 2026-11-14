# -*- coding: utf-8 -*-
"""Read vector lines and text from a PDF page - Python 3 standard library only.

Made for drawings exported from Revit / AutoCAD: it follows the page content stream (and the
forms it calls), applies the graphics transforms and returns every stroked line segment with its
colour and line width, plus text with its position. Curves are flattened to short lines.
Coordinates are PDF points (1/72 inch) with the origin at the bottom-left of the page, as shown.

    doc = PdfFile(path)
    page = doc.page(1)          # 1-based
    segs, texts, info = read_page(doc, page, include_fills=False)
    segs  -> [(x1, y1, x2, y2, '#RRGGBB', width_pt)]
    texts -> [(x, y, 'text', size_pt)]
"""
import re
import zlib
import math


class PdfError(Exception):
    pass


# ---------------------------------------------------------------------------- tokenizer / objects
class Ref(object):
    __slots__ = ('num', 'gen')

    def __init__(self, num, gen):
        self.num, self.gen = num, gen

    def __repr__(self):
        return 'Ref(%d)' % self.num


class Name(str):
    pass


class Stream(object):
    def __init__(self, dic, raw):
        self.dict, self.raw = dic, raw


WS = b' \t\r\n\x0c\x00'
DELIM = b'()<>[]{}/%'
_num_re = re.compile(rb'[+-]?(\d+\.?\d*|\.\d+)')


class Lexer(object):
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def skip(self):
        d, n = self.data, len(self.data)
        while self.pos < n:
            c = d[self.pos:self.pos + 1]
            if c in (b' ', b'\t', b'\r', b'\n', b'\x0c', b'\x00'):
                self.pos += 1
            elif c == b'%':
                while self.pos < n and d[self.pos:self.pos + 1] not in (b'\r', b'\n'):
                    self.pos += 1
            else:
                break

    def token(self):
        """Next raw token: bytes for keywords/numbers, or a parsed literal (str/bytes for strings)."""
        self.skip()
        d = self.data
        if self.pos >= len(d):
            return None
        c = d[self.pos:self.pos + 1]
        if c == b'/':
            j = self.pos + 1
            while j < len(d) and d[j:j + 1] not in WS and d[j:j + 1] not in DELIM:
                j += 1
            raw = d[self.pos + 1:j]
            self.pos = j
            name = re.sub(rb'#([0-9A-Fa-f]{2})', lambda m: bytes([int(m.group(1), 16)]), raw)
            return Name('/' + name.decode('latin-1'))
        if c == b'(':
            return ('str', self._literal())
        if c == b'<':
            if d[self.pos + 1:self.pos + 2] == b'<':
                self.pos += 2
                return b'<<'
            j = d.index(b'>', self.pos)
            hexs = re.sub(rb'\s', b'', d[self.pos + 1:j])
            if len(hexs) % 2:
                hexs += b'0'
            self.pos = j + 1
            return ('str', bytes.fromhex(hexs.decode('ascii', 'ignore')))
        if c == b'>':
            if d[self.pos + 1:self.pos + 2] == b'>':
                self.pos += 2
                return b'>>'
            self.pos += 1
            return b'>'
        if c in (b'[', b']', b'{', b'}'):
            self.pos += 1
            return c
        j = self.pos
        while j < len(d) and d[j:j + 1] not in WS and d[j:j + 1] not in DELIM:
            j += 1
        if j == self.pos:
            j += 1
        tok = d[self.pos:j]
        self.pos = j
        return tok

    def _literal(self):
        d = self.data
        i = self.pos + 1
        depth = 1
        out = bytearray()
        while i < len(d):
            c = d[i]
            if c == 0x5C:  # backslash
                i += 1
                e = d[i:i + 1]
                if e in b'nrtbf':
                    out += {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f'}[e]
                elif e in b'()\\':
                    out += e
                elif e.isdigit():
                    k = i
                    while k < i + 3 and d[k:k + 1].isdigit() and d[k:k + 1] in b'01234567':
                        k += 1
                    out.append(int(d[i:k], 8) & 0xFF)
                    i = k - 1
                elif e in (b'\r', b'\n'):
                    if e == b'\r' and d[i + 1:i + 2] == b'\n':
                        i += 1
                else:
                    out += e
            elif c == 0x28:
                depth += 1
                out.append(c)
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    self.pos = i + 1
                    return bytes(out)
                out.append(c)
            else:
                out.append(c)
            i += 1
        self.pos = i
        return bytes(out)


def parse_object(lex):
    """Parse one PDF object at the lexer position (dicts, arrays, refs, numbers, names, strings)."""
    tok = lex.token()
    return _obj_from(tok, lex)


def _obj_from(tok, lex):
    if tok is None:
        return None
    if isinstance(tok, Name):
        return tok
    if isinstance(tok, tuple):
        return tok[1]
    if tok == b'<<':
        d = {}
        while True:
            k = lex.token()
            if k == b'>>' or k is None:
                return d
            v = parse_object(lex)
            d[str(k)] = v
    if tok == b'[':
        arr = []
        while True:
            save = lex.pos
            t = lex.token()
            if t == b']' or t is None:
                return arr
            lex.pos = save
            arr.append(parse_object(lex))
    if tok in (b'true', b'false'):
        return tok == b'true'
    if tok == b'null':
        return None
    if _num_re.fullmatch(tok or b''):
        # maybe "num gen R"
        save = lex.pos
        t2 = lex.token()
        if isinstance(t2, bytes) and t2.isdigit():
            t3 = lex.token()
            if t3 == b'R':
                return Ref(int(tok), int(t2))
        lex.pos = save
        return float(tok) if (b'.' in tok) else int(tok)
    return tok


# ---------------------------------------------------------------------------- file
_obj_re = re.compile(rb'(?<![0-9])(\d+)\s+(\d+)\s+obj\b')


class PdfFile(object):
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.data = f.read()
        if not self.data.startswith(b'%PDF') and b'%PDF' not in self.data[:1024]:
            raise PdfError('Not a PDF file: %s' % path)
        self.objects = {}
        self._scan()
        self._pages = None

    def _scan(self):
        d = self.data
        for m in _obj_re.finditer(d):
            num = int(m.group(1))
            lex = Lexer(d, m.end())
            try:
                obj = parse_object(lex)
            except Exception:
                continue
            lex.skip()
            if d[lex.pos:lex.pos + 6] == b'stream':
                start = lex.pos + 6
                if d[start:start + 2] == b'\r\n':
                    start += 2
                elif d[start:start + 1] in (b'\n', b'\r'):
                    start += 1
                length = obj.get('/Length') if isinstance(obj, dict) else None
                end = -1
                if isinstance(length, int) and d[start + length:start + length + 30].lstrip().startswith(b'endstream'):
                    end = start + length
                if end < 0:
                    end = d.find(b'endstream', start)
                    if end < 0:
                        continue
                    while end > start and d[end - 1:end] in (b'\r', b'\n'):
                        end -= 1
                obj = Stream(obj if isinstance(obj, dict) else {}, d[start:end])
            self.objects[num] = obj        # later definitions (incremental updates) win
        # objects inside object streams
        for num, obj in list(self.objects.items()):
            if isinstance(obj, Stream) and obj.dict.get('/Type') == '/ObjStm':
                try:
                    self._unpack_objstm(obj)
                except Exception:
                    pass

    def _unpack_objstm(self, st):
        data = decode_stream(self, st)
        n = int(self.resolve(st.dict.get('/N')))
        first = int(self.resolve(st.dict.get('/First')))
        head = Lexer(data[:first])
        pairs = []
        for _ in range(n):
            a = int(head.token())
            b = int(head.token())
            pairs.append((a, b))
        for num, off in pairs:
            if num in self.objects and not isinstance(self.objects[num], Stream):
                continue
            lex = Lexer(data, first + off)
            try:
                self.objects.setdefault(num, parse_object(lex))
            except Exception:
                pass

    def resolve(self, o, depth=0):
        while isinstance(o, Ref) and depth < 20:
            o = self.objects.get(o.num)
            depth += 1
        return o

    # pages in document order
    def pages(self):
        if self._pages is not None:
            return self._pages
        root = None
        for obj in self.objects.values():
            dct = obj.dict if isinstance(obj, Stream) else obj
            if isinstance(dct, dict) and dct.get('/Type') == '/Catalog':
                root = dct
        pages = []
        if root is not None:
            self._walk(self.resolve(root.get('/Pages')), {}, pages, 0)
        if not pages:   # fallback: every /Page object
            for num in sorted(self.objects):
                o = self.objects[num]
                if isinstance(o, dict) and o.get('/Type') == '/Page':
                    pages.append(o)
        self._pages = pages
        return pages

    def _walk(self, node, inherited, out, depth):
        if not isinstance(node, dict) or depth > 30:
            return
        inh = dict(inherited)
        for key in ('/Resources', '/MediaBox', '/CropBox', '/Rotate'):
            if key in node:
                inh[key] = node[key]
        if node.get('/Type') == '/Page' or '/Kids' not in node:
            page = dict(inh)
            page.update(node)
            out.append(page)
            return
        for kid in self.resolve(node.get('/Kids')) or []:
            self._walk(self.resolve(kid), inh, out, depth + 1)

    def page(self, number):
        pages = self.pages()
        if not pages:
            raise PdfError('No pages found in the PDF.')
        if number < 1 or number > len(pages):
            raise PdfError('Page %d does not exist (the PDF has %d pages).' % (number, len(pages)))
        return pages[number - 1]


def _png_unpredict(data, columns, colors=1, bpc=8):
    bpp = max(1, colors * bpc // 8)
    row_len = columns * bpp
    out = bytearray()
    prev = bytearray(row_len)
    i = 0
    while i + 1 + row_len <= len(data) + 1 and i < len(data):
        ft = data[i]
        row = bytearray(data[i + 1:i + 1 + row_len])
        for k in range(len(row)):
            a = row[k - bpp] if k >= bpp else 0
            b = prev[k]
            c = prev[k - bpp] if k >= bpp else 0
            if ft == 1:
                row[k] = (row[k] + a) & 0xFF
            elif ft == 2:
                row[k] = (row[k] + b) & 0xFF
            elif ft == 3:
                row[k] = (row[k] + ((a + b) >> 1)) & 0xFF
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[k] = (row[k] + pr) & 0xFF
        out += row
        prev = row
        i += 1 + row_len
    return bytes(out)


def _a85(data):
    data = re.sub(rb'\s', b'', data)
    if data.startswith(b'<~'):
        data = data[2:]
    end = data.find(b'~>')
    if end >= 0:
        data = data[:end]
    out = bytearray()
    group = []
    for ch in data:
        if ch == ord('z') and not group:
            out += b'\0\0\0\0'
            continue
        group.append(ch - 33)
        if len(group) == 5:
            v = 0
            for g in group:
                v = v * 85 + g
            out += v.to_bytes(4, 'big')
            group = []
    if group:
        n = len(group)
        group += [84] * (5 - n)
        v = 0
        for g in group:
            v = v * 85 + g
        out += v.to_bytes(4, 'big')[:n - 1]
    return bytes(out)


def decode_stream(pdf, st):
    data = st.raw
    filters = pdf.resolve(st.dict.get('/Filter'))
    parms = pdf.resolve(st.dict.get('/DecodeParms'))
    if filters is None:
        return data
    if not isinstance(filters, list):
        filters = [filters]
        parms = [parms]
    elif not isinstance(parms, list):
        parms = [parms] * len(filters)
    for f, p in zip(filters, parms):
        f = pdf.resolve(f)
        p = pdf.resolve(p) or {}
        if f in ('/FlateDecode', '/Fl'):
            try:
                data = zlib.decompress(data)
            except zlib.error:
                data = zlib.decompressobj().decompress(data)
            pred = int(pdf.resolve(p.get('/Predictor', 1)) or 1) if isinstance(p, dict) else 1
            if pred >= 10:
                data = _png_unpredict(data, int(pdf.resolve(p.get('/Columns', 1))),
                                      int(pdf.resolve(p.get('/Colors', 1))), int(pdf.resolve(p.get('/BitsPerComponent', 8))))
        elif f in ('/ASCIIHexDecode', '/AHx'):
            hexs = re.sub(rb'\s', b'', data).rstrip(b'>')
            if len(hexs) % 2:
                hexs += b'0'
            data = bytes.fromhex(hexs.decode('ascii', 'ignore'))
        elif f in ('/ASCII85Decode', '/A85'):
            data = _a85(data)
        else:
            raise PdfError('Unsupported stream filter %s' % f)
    return data


# ---------------------------------------------------------------------------- content interpreter
def _mul(a, b):
    """3x3 affine matrices as 6-tuples (a b c d e f): result = a * b."""
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


def _apply(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _hex(rgb):
    r, g, b = [max(0, min(255, int(round(v * 255)))) for v in rgb]
    return '#%02X%02X%02X' % (r, g, b)


def _color(vals):
    vals = [float(v) for v in vals if isinstance(v, (int, float))]
    if len(vals) == 1:
        return (vals[0], vals[0], vals[0])
    if len(vals) == 3:
        return tuple(vals)
    if len(vals) == 4:
        c, m, y, k = vals
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return (0.0, 0.0, 0.0)


class _State(object):
    def __init__(self):
        self.ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        self.stroke = (0.0, 0.0, 0.0)
        self.fill = (0.0, 0.0, 0.0)
        self.width = 1.0
        self.font = None
        self.font_size = 10.0
        self.leading = 0.0

    def copy(self):
        s = _State()
        s.__dict__.update(self.__dict__)
        return s


def _tounicode(pdf, font):
    """Map from char codes to text using the font's /ToUnicode CMap (best effort)."""
    cmap = {}
    tu = pdf.resolve(font.get('/ToUnicode')) if isinstance(font, dict) else None
    if not isinstance(tu, Stream):
        return None, 1
    try:
        data = decode_stream(pdf, tu)
    except Exception:
        return None, 1
    width = 1
    for block in re.findall(rb'beginbfchar(.*?)endbfchar', data, re.S):
        for src, dst in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            width = max(width, len(src) // 2)
            try:
                cmap[int(src, 16)] = bytes.fromhex(dst.decode()).decode('utf-16-be', 'ignore')
            except Exception:
                pass
    for block in re.findall(rb'beginbfrange(.*?)endbfrange', data, re.S):
        for a, b, dst in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]+>)', block):
            width = max(width, len(a) // 2)
            start, end = int(a, 16), int(b, 16)
            if dst.startswith(b'['):
                for k, h in enumerate(re.findall(rb'<([0-9A-Fa-f]+)>', dst)):
                    try:
                        cmap[start + k] = bytes.fromhex(h.decode()).decode('utf-16-be', 'ignore')
                    except Exception:
                        pass
                continue
            base = int(dst.strip(b'<>'), 16)
            for k in range(start, min(end, start + 5000) + 1):
                try:
                    cmap[k] = chr(base + k - start)
                except Exception:
                    pass
    return cmap, width


def _decode_text(raw, finfo):
    cmap, width = finfo if finfo else (None, 1)
    if cmap:
        out = []
        for i in range(0, len(raw) - width + 1, width):
            code = int.from_bytes(raw[i:i + width], 'big')
            out.append(cmap.get(code, ''))
        return ''.join(out)
    return ''.join(ch if (ch.isprintable() or ch == ' ') else '' for ch in raw.decode('latin-1'))


class Reader(object):
    def __init__(self, pdf, include_fills=False, bezier_steps=6, max_segments=400000):
        self.pdf = pdf
        self.include_fills = include_fills
        self.steps = bezier_steps
        self.segs = []
        self.texts = []
        self.max_segments = max_segments
        self.fonts = {}
        self.forms_seen = 0

    def run(self, data, resources, state, depth=0):
        pdf = self.pdf
        resources = pdf.resolve(resources) or {}
        lex = Lexer(data)
        ops = []
        st = state
        stack = []
        path = []          # list of subpaths, each = list of (x, y) in user space -> converted at paint time
        cur = None
        tm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        tlm = tm
        while True:
            save = lex.pos
            tok = lex.token()
            if tok is None:
                break
            if isinstance(tok, (Name, tuple)) or tok in (b'[', b'<<'):
                lex.pos = save
                ops.append(parse_object(lex))
                continue
            if isinstance(tok, bytes) and _num_re.fullmatch(tok):
                ops.append(float(tok))
                continue
            op = tok
            try:
                if op == b'q':
                    stack.append(st.copy())
                elif op == b'Q':
                    if stack:
                        st = stack.pop()
                elif op == b'cm' and len(ops) >= 6:
                    st.ctm = _mul(tuple(ops[-6:]), st.ctm)
                elif op == b'w' and ops:
                    st.width = float(ops[-1])
                elif op in (b'RG', b'K', b'G'):
                    st.stroke = _color(ops)
                elif op in (b'rg', b'k', b'g'):
                    st.fill = _color(ops)
                elif op in (b'SC', b'SCN'):
                    st.stroke = _color(ops)
                elif op in (b'sc', b'scn'):
                    st.fill = _color(ops)
                elif op == b'm' and len(ops) >= 2:
                    cur = _apply(st.ctm, ops[-2], ops[-1])
                    path.append([cur])
                elif op == b'l' and len(ops) >= 2:
                    cur = _apply(st.ctm, ops[-2], ops[-1])
                    if not path:
                        path.append([cur])
                    else:
                        path[-1].append(cur)
                elif op in (b'c', b'v', b'y') and path:
                    p0 = path[-1][-1]
                    if op == b'c' and len(ops) >= 6:
                        p1 = _apply(st.ctm, ops[-6], ops[-5]); p2 = _apply(st.ctm, ops[-4], ops[-3]); p3 = _apply(st.ctm, ops[-2], ops[-1])
                    elif op == b'v' and len(ops) >= 4:
                        p1 = p0; p2 = _apply(st.ctm, ops[-4], ops[-3]); p3 = _apply(st.ctm, ops[-2], ops[-1])
                    elif len(ops) >= 4:
                        p1 = _apply(st.ctm, ops[-4], ops[-3]); p3 = _apply(st.ctm, ops[-2], ops[-1]); p2 = p3
                    else:
                        ops = []
                        continue
                    for k in range(1, self.steps + 1):
                        t = k / float(self.steps)
                        mt = 1 - t
                        x = mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0]
                        y = mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]
                        path[-1].append((x, y))
                    cur = p3
                elif op == b're' and len(ops) >= 4:
                    x, y, w, h = ops[-4:]
                    pts = [_apply(st.ctm, x, y), _apply(st.ctm, x + w, y), _apply(st.ctm, x + w, y + h),
                           _apply(st.ctm, x, y + h), _apply(st.ctm, x, y)]
                    path.append(pts)
                elif op == b'h' and path and len(path[-1]) > 1:
                    path[-1].append(path[-1][0])
                elif op in (b'S', b's', b'B', b'B*', b'b', b'b*'):
                    if op in (b's', b'b', b'b*') and path and len(path[-1]) > 1:
                        path[-1].append(path[-1][0])
                    self._emit(path, st.stroke, st.width * _scale(st.ctm))
                    path = []
                elif op in (b'f', b'F', b'f*'):
                    if self.include_fills:
                        self._emit(path, st.fill, 0.0)
                    path = []
                elif op == b'n':
                    path = []
                elif op == b'Do' and ops and isinstance(ops[-1], Name):
                    self._do(ops[-1], resources, st, depth)
                elif op == b'BT':
                    tm = tlm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
                elif op == b'Tf' and len(ops) >= 2:
                    st.font = ops[-2]
                    st.font_size = float(ops[-1])
                elif op == b'TL' and ops:
                    st.leading = float(ops[-1])
                elif op in (b'Td', b'TD') and len(ops) >= 2:
                    if op == b'TD':
                        st.leading = -float(ops[-1])
                    tlm = _mul((1, 0, 0, 1, float(ops[-2]), float(ops[-1])), tlm)
                    tm = tlm
                elif op == b'Tm' and len(ops) >= 6:
                    tm = tlm = tuple(float(v) for v in ops[-6:])
                elif op == b'T*':
                    tlm = _mul((1, 0, 0, 1, 0, -st.leading), tlm)
                    tm = tlm
                elif op in (b'Tj', b"'", b'"', b'TJ'):
                    if op in (b"'", b'"'):
                        tlm = _mul((1, 0, 0, 1, 0, -st.leading), tlm)
                        tm = tlm
                    raw = b''
                    if op == b'TJ' and ops and isinstance(ops[-1], list):
                        raw = b''.join(x for x in ops[-1] if isinstance(x, bytes))
                    elif ops and isinstance(ops[-1], bytes):
                        raw = ops[-1]
                    self._text(raw, resources, st, tm)
                elif op == b'BI':
                    end = data.find(b'EI', lex.pos)
                    lex.pos = end + 2 if end >= 0 else len(data)
            except Exception:
                pass
            ops = []
            if len(self.segs) >= self.max_segments:
                break

    def _emit(self, path, rgb, width):
        color = _hex(rgb)
        for sub in path:
            for i in range(len(sub) - 1):
                a, b = sub[i], sub[i + 1]
                if abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6:
                    continue
                self.segs.append((a[0], a[1], b[0], b[1], color, round(width, 3)))

    def _do(self, name, resources, st, depth):
        if depth > 8:
            return
        pdf = self.pdf
        xobjs = pdf.resolve(resources.get('/XObject')) or {}
        xo = pdf.resolve(xobjs.get(str(name)))
        if not isinstance(xo, Stream) or xo.dict.get('/Subtype') != '/Form':
            return
        self.forms_seen += 1
        child = st.copy()
        m = pdf.resolve(xo.dict.get('/Matrix'))
        if isinstance(m, list) and len(m) == 6:
            child.ctm = _mul(tuple(float(pdf.resolve(v)) for v in m), st.ctm)
        try:
            data = decode_stream(pdf, xo)
        except Exception:
            return
        self.run(data, xo.dict.get('/Resources') or resources, child, depth + 1)

    def _text(self, raw, resources, st, tm):
        if not raw:
            return
        fname = str(st.font) if st.font else None
        finfo = self.fonts.get(fname)
        if fname and fname not in self.fonts:
            fonts = self.pdf.resolve(resources.get('/Font')) or {}
            font = self.pdf.resolve(fonts.get(fname))
            finfo = _tounicode(self.pdf, font) if isinstance(font, dict) else None
            if finfo and finfo[0] is None:
                sub = font.get('/Subtype') if isinstance(font, dict) else None
                finfo = (None, 2 if sub == '/Type0' else 1)
            self.fonts[fname] = finfo
        text = _decode_text(raw, finfo).strip()
        if not text:
            return
        m = _mul(tm, st.ctm)
        x, y = m[4], m[5]
        size = st.font_size * math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))
        self.texts.append((x, y, text, round(size, 2)))


def _scale(m):
    return math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) or 1.0


def read_page(pdf, page, include_fills=False):
    contents = pdf.resolve(page.get('/Contents'))
    parts = contents if isinstance(contents, list) else [contents]
    data = b''
    for p in parts:
        st = pdf.resolve(p)
        if isinstance(st, Stream):
            try:
                data += decode_stream(pdf, st) + b'\n'
            except Exception:
                pass
    box = pdf.resolve(page.get('/CropBox') or page.get('/MediaBox')) or [0, 0, 612, 792]
    box = [float(pdf.resolve(v)) for v in box]
    rotate = int(pdf.resolve(page.get('/Rotate')) or 0) % 360
    reader = Reader(pdf, include_fills=include_fills)
    reader.run(data, page.get('/Resources'), _State())
    segs, texts = reader.segs, reader.texts
    # shown orientation: origin bottom-left of the visible page
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    def rot(x, y):
        x, y = x - x0, y - y0
        if rotate == 90:
            return y, w - x
        if rotate == 180:
            return w - x, h - y
        if rotate == 270:
            return h - y, x
        return x, y
    segs = [rot(a, b) + rot(c, d) + (col, wd) for (a, b, c, d, col, wd) in segs]
    texts = [rot(x, y) + (t, s) for (x, y, t, s) in texts]
    size = (h, w) if rotate in (90, 270) else (w, h)
    info = {'page_size_pt': [round(size[0], 1), round(size[1], 1)],
            'page_size_mm': [round(size[0] * 25.4 / 72, 1), round(size[1] * 25.4 / 72, 1)],
            'rotate': rotate, 'forms': reader.forms_seen}
    return segs, texts, info
