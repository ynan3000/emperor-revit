// Emperor - builds the data of an AutoCAD OLE2FRAME that holds a picture ("Paintbrush Picture" embedded
// object), the same thing AutoCAD creates when a bitmap is pasted into a drawing.
// Layout verified against an OLE2FRAME written by AutoCAD 2018 (see docs in the Emperor repository).
using System;
using System.Collections.Generic;
using System.IO;

namespace EmperorDwg
{
	public sealed class Bitmap24
	{
		public int Width, Height;
		/// <summary>BITMAPINFOHEADER (40 bytes) + bottom-up 24-bit pixel rows, each padded to 4 bytes.</summary>
		public byte[] Dib;

		/// <summary>Reads an uncompressed 24 or 32 bit .bmp file (what WPF's BmpBitmapEncoder writes).</summary>
		public static Bitmap24 FromBmpFile(byte[] bmp)
		{
			if (bmp == null || bmp.Length < 54 || bmp[0] != (byte)'B' || bmp[1] != (byte)'M')
				throw new InvalidDataException("not a BMP file");
			int offBits = BitConverter.ToInt32(bmp, 10);
			int headerSize = BitConverter.ToInt32(bmp, 14);
			int w = BitConverter.ToInt32(bmp, 18), h = BitConverter.ToInt32(bmp, 22);
			int bpp = BitConverter.ToInt16(bmp, 28), compression = BitConverter.ToInt32(bmp, 30);
			if (headerSize < 40 || (bpp != 24 && bpp != 32) || (compression != 0 && compression != 3) || w <= 0 || h == 0)
				throw new InvalidDataException("unsupported BMP (need uncompressed 24 / 32 bit)");
			bool topDown = h < 0;
			if (topDown) h = -h;
			int srcStride = ((w * bpp + 31) / 32) * 4, stride = ((w * 24 + 31) / 32) * 4;
			if (offBits + (long)srcStride * h > bmp.Length) throw new InvalidDataException("BMP is cut short");
			byte[] dib = new byte[40 + stride * h];
			using (var ms = new MemoryStream(dib))
			using (var bw = new BinaryWriter(ms))
			{
				bw.Write(40); bw.Write(w); bw.Write(h); bw.Write((short)1); bw.Write((short)24);
				bw.Write(0); bw.Write(stride * h); bw.Write(0); bw.Write(0); bw.Write(0); bw.Write(0);
			}
			int step = bpp / 8;
			for (int y = 0; y < h; y++)
			{
				int src = offBits + (topDown ? (h - 1 - y) : y) * srcStride, dst = 40 + y * stride;
				if (bpp == 24) Buffer.BlockCopy(bmp, src, dib, dst, w * 3);
				else for (int x = 0; x < w; x++) { dib[dst + x * 3] = bmp[src + x * step]; dib[dst + x * 3 + 1] = bmp[src + x * step + 1]; dib[dst + x * 3 + 2] = bmp[src + x * step + 2]; }
			}
			return new Bitmap24 { Width = w, Height = h, Dib = dib };
		}
	}

	public static class OleImage
	{
		private static readonly Guid PBrush = new Guid("0003000A-0000-0000-C000-000000000046");

		private static readonly byte[] CompObj = hex(
			"0100feff030a0000ffffffff0a00030000000000c000000000000046070000005042727573680007000000" +
			"504272757368000700000050427275736800f439b271000000000000000000000000");

		private static readonly byte[] OleStream = hex("0100000200000000000000000000000000000000");

		private static byte[] hex(string s)
		{
			byte[] b = new byte[s.Length / 2];
			for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(s.Substring(i * 2, 2), 16);
			return b;
		}

		/// <summary>Size of the picture in 0.01 mm at 96 dpi, kept inside what a 16-bit field can hold.</summary>
		public static void Himetric(Bitmap24 bmp, out int w, out int h)
		{
			double hw = bmp.Width * 2540.0 / 96.0, hh = bmp.Height * 2540.0 / 96.0;
			double k = Math.Max(hw, hh) / 32000.0;
			if (k > 1) { hw /= k; hh /= k; }
			w = Math.Max(1, (int)Math.Round(hw)); h = Math.Max(1, (int)Math.Round(hh));
		}

		/// <summary>The embedded object itself: a compound file with the picture and its presentation.</summary>
		public static byte[] BuildObject(Bitmap24 bmp)
		{
			int hmW, hmH; Himetric(bmp, out hmW, out hmH);
			if (bmp.Width > 32767 || bmp.Height > 32767) throw new InvalidDataException("picture is too large");

			// \1Ole10Native : length + a complete .bmp file
			var native = new MemoryStream();
			var nw = new BinaryWriter(native);
			nw.Write(14 + bmp.Dib.Length + 14);
			nw.Write((byte)'B'); nw.Write((byte)'M'); nw.Write(14 + bmp.Dib.Length); nw.Write(0); nw.Write(54);
			nw.Write(bmp.Dib);
			nw.Write(new byte[14]);                    // Paint leaves 14 empty bytes after the file

			// \2OlePres000 : what is drawn - a Windows metafile that stretches the bitmap
			var wmf = new MemoryStream();
			var mw = new BinaryWriter(wmf);
			int recWords = 3 + 10 + bmp.Dib.Length / 2;
			int totalWords = 9 + 4 + 5 + 5 + recWords + 3;
			mw.Write((short)1); mw.Write((short)9); mw.Write((short)0x0300); mw.Write(totalWords); mw.Write((short)0); mw.Write(recWords); mw.Write((short)0);
			mw.Write(4); mw.Write((short)0x0103); mw.Write((short)8);                                           // SetMapMode(MM_ANISOTROPIC)
			mw.Write(5); mw.Write((short)0x020C); mw.Write((short)(-bmp.Height)); mw.Write((short)bmp.Width);    // SetWindowExt
			mw.Write(5); mw.Write((short)0x020B); mw.Write((short)0); mw.Write((short)0);                        // SetWindowOrg
			mw.Write(recWords); mw.Write((short)0x0B41);                                                         // DibStretchBlt
			mw.Write(0x00CC0020);                                                                                // SRCCOPY
			mw.Write((short)bmp.Height); mw.Write((short)bmp.Width); mw.Write((short)0); mw.Write((short)0);
			mw.Write((short)(-bmp.Height)); mw.Write((short)bmp.Width); mw.Write((short)0); mw.Write((short)0);
			mw.Write(bmp.Dib);
			mw.Write(3); mw.Write((short)0);                                                                     // end
			byte[] wmfData = wmf.ToArray();

			var pres = new MemoryStream();
			var pw = new BinaryWriter(pres);
			pw.Write(-1); pw.Write(3);                 // clipboard format CF_METAFILEPICT
			pw.Write(4);                               // no target device
			pw.Write(1); pw.Write(-1); pw.Write(2); pw.Write(0);   // aspect content, lindex, advf, reserved
			pw.Write(hmW); pw.Write(hmH);
			pw.Write(wmfData.Length); pw.Write(wmfData);
			pw.Write(new byte[18]); pw.Write(0x494E414E); pw.Write(0);   // reserved + "NANI" table of contents (empty)

			var streams = new List<CfbStream>
			{
				new CfbStream("\u0001Ole", OleStream),
				new CfbStream("\u0001CompObj", CompObj),
				new CfbStream("\u0001Ole10Native", native.ToArray()),
				new CfbStream("\u0002OlePres000", pres.ToArray()),
			};
			return Cfb.Build(PBrush, streams);
		}

		/// <summary>The complete binary data of the OLE2FRAME: frame header + the embedded object.
		/// Corners are in the coordinates of the space the frame sits in.</summary>
		public static byte[] BuildFrameData(Bitmap24 bmp, double left, double bottom, double right, double top, double z, bool paperSpace, int itemId)
		{
			int hmW, hmH; Himetric(bmp, out hmW, out hmH);
			byte[] obj = BuildObject(bmp);
			var ms = new MemoryStream(obj.Length + 128);
			var w = new BinaryWriter(ms);
			w.Write((byte)(0x80 | (paperSpace ? 1 : 0))); w.Write((byte)0x55);
			w.Write(left); w.Write(top); w.Write(z);          // upper left
			w.Write(right); w.Write(top); w.Write(z);         // upper right
			w.Write(right); w.Write(bottom); w.Write(z);      // lower right
			w.Write(left); w.Write(bottom); w.Write(z);       // lower left
			w.Write((short)hmW); w.Write((short)hmH);
			w.Write(1); w.Write(0x100); w.Write(itemId); w.Write(1);
			w.Write((short)0); w.Write(1);
			w.Write(obj.Length); w.Write(obj);
			return ms.ToArray();
		}
	}
}
