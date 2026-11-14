# -*- coding: ascii -*-
"""Emperor - "Bind images as OLE" for exported DWG files.

Revit exports every image on a sheet (title block logos, pictures) as a separate file that the DWG
only links to. This module opens the exported DWG, stores each picture INSIDE the drawing as an OLE
object (what AutoCAD does when a bitmap is pasted) and saves it again - no AutoCAD needed.

The DWG work is done by lib/dwg/EmperorDwg_1_1.dll (.NET 8, so Revit 2025 and newer). The DLL is copied
to %LOCALAPPDATA%\\Emperor\\dwg and loaded from there, so the extension folder is never locked.
Images that cannot be embedded safely (rotated, clipped to a polygon, inside a rotated block) stay
linked and are reported.
"""
import os

DLL_NAME = 'EmperorDwg_1_1.dll'
MAX_WIDTH = 1600        # AutoCAD shows very large OLE pictures blank - bigger pictures are scaled down
MAX_HEIGHT = 1200

_state = {'asm': None, 'error': None}


def available():
    """(True, '') when the option can run in this Revit, else (False, why)."""
    try:
        import System
        if System.Environment.Version.Major < 8:
            return False, 'needs Revit 2025 or newer'
    except Exception as ex:
        return False, 'the .NET version could not be read (%s)' % ex
    if not os.path.isfile(_source_dll()):
        return False, 'lib\\dwg\\%s is missing from the Emperor folder' % DLL_NAME
    return True, ''


def _source_dll():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dwg', DLL_NAME)


def _private_dll():
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or os.path.expanduser('~')
    folder = os.path.join(base, 'Emperor', 'dwg')
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return os.path.join(folder, DLL_NAME)


def _assembly():
    if _state['asm'] is not None:
        return _state['asm']
    src, dst = _source_dll(), _private_dll()
    try:
        if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
            import shutil
            shutil.copyfile(src, dst)
    except Exception:
        if not os.path.isfile(dst):         # could not copy and there is no earlier copy
            dst = src
    from System.Reflection import Assembly
    _state['asm'] = Assembly.LoadFrom(dst)
    return _state['asm']


def _load_bmp(path, max_w, max_h):
    """The picture as an uncompressed .bmp file (bytes): on white, no larger than max_w x max_h."""
    import clr
    for name in ('WindowsBase', 'PresentationCore'):
        try:
            clr.AddReference(name)
        except Exception:
            pass
    from System import Uri
    from System.IO import MemoryStream
    from System.Windows import Rect
    from System.Windows.Media import DrawingVisual, Brushes, PixelFormats, RenderOptions, BitmapScalingMode
    from System.Windows.Media.Imaging import (BitmapImage, BitmapCacheOption, RenderTargetBitmap, BmpBitmapEncoder,
                                              BitmapFrame, FormatConvertedBitmap)
    img = BitmapImage()
    img.BeginInit()
    img.CacheOption = BitmapCacheOption.OnLoad          # read it now and let go of the file
    img.UriSource = Uri(path)
    img.EndInit()
    w, h = img.PixelWidth, img.PixelHeight
    k = min(1.0, float(max_w) / w, float(max_h) / h)
    tw, th = max(1, int(round(w * k))), max(1, int(round(h * k)))
    visual = DrawingVisual()
    RenderOptions.SetBitmapScalingMode(visual, BitmapScalingMode.HighQuality)
    dc = visual.RenderOpen()
    dc.DrawRectangle(Brushes.White, None, Rect(0, 0, tw, th))   # transparent PNG -> white paper
    dc.DrawImage(img, Rect(0, 0, tw, th))
    dc.Close()
    target = RenderTargetBitmap(tw, th, 96, 96, PixelFormats.Pbgra32)
    target.Render(visual)
    encoder = BmpBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(FormatConvertedBitmap(target, PixelFormats.Bgr24, None, 0)))
    stream = MemoryStream()
    encoder.Save(stream)
    return stream.ToArray()


def bind(path):
    """Embed the linked images of one DWG (the file is replaced only when the new one opens again).
    Returns a dict: converted, created, kept, saved, messages, warnings, freed, kept_files."""
    from System import Func, Array, Byte, Object
    asm = _assembly()
    binder = asm.GetType('EmperorDwg.ImageBinder')
    if binder is None:
        raise Exception('%s does not contain the image binder' % DLL_NAME)
    loader = Func[str, int, int, Array[Byte]](_load_bmp)
    try:
        r = binder.GetMethod('Bind').Invoke(None, Array[Object]([path, path, loader, MAX_WIDTH, MAX_HEIGHT]))
    except Exception as ex:
        inner = getattr(ex, 'InnerException', None)
        clr_ex = getattr(ex, 'clsException', None)
        if inner is None and clr_ex is not None:
            inner = getattr(clr_ex, 'InnerException', None)
        raise Exception('%s' % (inner.Message if inner is not None else ex))
    return {'converted': int(r.Converted), 'created': int(r.Created), 'kept': int(r.Kept), 'saved': bool(r.Saved),
            'messages': [u'%s' % m for m in r.Messages], 'warnings': [u'%s' % m for m in r.Warnings],
            'freed': [u'%s' % m for m in r.FreedFiles], 'kept_files': [u'%s' % m for m in r.KeptFiles]}


def bind_files(paths, problems, delete_images=True):
    """Embed the images of several DWG files that came from ONE export. Notes go to 'problems'.
    The image files nobody links to any more are deleted. Returns the number of embedded images."""
    ok, why = available()
    if not ok:
        problems.append('Bind images as OLE was skipped: %s.' % why)
        return 0
    done = 0
    freed, still_used = set(), set()
    for path in paths:
        name = os.path.basename(path)
        try:
            r = bind(path)
        except Exception as ex:
            problems.append(u'%s: images could not be bound as OLE (%s) - the file was left as Revit exported it.' % (name, ex))
            # this drawing still links to its images: do not delete anything it may need
            delete_images = False
            continue
        done += r['converted']
        freed.update(os.path.normcase(os.path.abspath(f)) for f in r['freed'])
        still_used.update(os.path.normcase(os.path.abspath(f)) for f in r['kept_files'])
        for m in r['messages']:
            if r['kept']:
                problems.append(u'%s: %s' % (name, m))
        for m in r['warnings']:
            problems.append(u'%s: OLE note - %s' % (name, m))
    if delete_images:
        for f in sorted(freed - still_used):
            try:
                if os.path.isfile(f):
                    os.remove(f)
            except Exception as ex:
                problems.append(u'%s could not be deleted (%s).' % (os.path.basename(f), ex))
    return done
