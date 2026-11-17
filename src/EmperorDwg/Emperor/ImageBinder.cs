// Emperor - "Bind images as OLE": replaces the linked raster images of a DWG (as exported by Revit)
// with embedded OLE pictures, so the drawing is one file with no image references.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using ACadSharp;
using ACadSharp.Entities;
using ACadSharp.IO;
using ACadSharp.Objects;
using ACadSharp.Tables;
using ACadSharp.XData;
using CSMath;

namespace EmperorDwg
{
	public sealed class BindResult
	{
		/// <summary>Linked images replaced by embedded pictures.</summary>
		public int Converted;
		/// <summary>Embedded pictures created (an image inside a block used several times gives several).</summary>
		public int Created;
		/// <summary>Images left as they were (the reason is in Messages).</summary>
		public int Kept;
		public bool Saved;
		public List<string> Messages = new List<string>();
		/// <summary>Image files that are no longer referenced by the drawing.</summary>
		public List<string> FreedFiles = new List<string>();
		/// <summary>Image files the drawing still links to (images that could not be embedded).</summary>
		public List<string> KeptFiles = new List<string>();
		public List<string> Warnings = new List<string>();
	}

	public static class ImageBinder
	{
		private const double EPS = 1e-6;

		private sealed class Placement
		{
			public BlockRecord Space;
			public double Scale = 1, Dx, Dy, Z;
		}

		/// <summary>
		/// Reads dwgIn, embeds its images and writes dwgOut (may be the same path).
		/// loadBmp(path, maxWidth, maxHeight) returns the picture as an uncompressed 24 / 32 bit .bmp file,
		/// already flattened on white and no larger than the limits - or null when it cannot be read.
		/// Nothing is written when no image could be converted.
		/// </summary>
		public static BindResult Bind(string dwgIn, string dwgOut, Func<string, int, int, byte[]> loadBmp, int maxWidth, int maxHeight)
		{
			var result = new BindResult();
			CadDocument doc;
			using (var reader = new DwgReader(dwgIn))
			{
				reader.OnNotification += (s, e) => { if (e.NotificationType == NotificationType.Error) result.Warnings.Add("read: " + e.Message); };
				doc = reader.Read();
			}

			// every insert, by the block it shows
			var uses = new Dictionary<BlockRecord, List<KeyValuePair<Insert, BlockRecord>>>();
			var images = new List<KeyValuePair<RasterImage, BlockRecord>>();
			foreach (BlockRecord br in doc.BlockRecords)
				foreach (Entity e in br.Entities)
				{
					if (e is Insert ins && ins.Block != null)
					{
						if (!uses.TryGetValue(ins.Block, out var list)) uses[ins.Block] = list = new List<KeyValuePair<Insert, BlockRecord>>();
						list.Add(new KeyValuePair<Insert, BlockRecord>(ins, br));
					}
					else if (e is RasterImage img) images.Add(new KeyValuePair<RasterImage, BlockRecord>(img, br));
				}
			if (images.Count == 0)
			{
				result.Messages.Add("no linked images in this drawing");
				return result;
			}

			string folder = Path.GetDirectoryName(Path.GetFullPath(dwgIn));
			var cache = new Dictionary<string, Bitmap24>(StringComparer.OrdinalIgnoreCase);
			var freed = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
			var usedDefs = new HashSet<ImageDefinition>();
			int itemId = 1;
			foreach (BlockRecord br in doc.BlockRecords)
				foreach (Entity e in br.Entities)
					if (e is Ole2Frame) itemId++;

			foreach (var pair in images)
			{
				RasterImage img = pair.Key; BlockRecord owner = pair.Value;
				string file = img.Definition != null ? img.Definition.FileName : null;
				string label = string.IsNullOrEmpty(file) ? "(image without a file)" : fileName(file);
				string why = null;
				List<Placement> places = null;
				Bitmap24 bmp = null;

				if (string.IsNullOrEmpty(file)) why = "it has no file";
				else if (Math.Abs(img.UVector.Y) > EPS || Math.Abs(img.UVector.Z) > EPS || Math.Abs(img.VVector.X) > EPS || Math.Abs(img.VVector.Z) > EPS
					|| img.UVector.X <= 0 || img.VVector.Y <= 0) why = "it is rotated or mirrored";
				else if (img.ClippingState && img.ClipBoundaryVertices != null && img.ClipBoundaryVertices.Count > 2) why = "it is clipped to a polygon";
				else
				{
					places = new List<Placement>();
					if (!resolve(owner, new Placement(), uses, places, 0)) { why = "it is inside a block that is rotated, mirrored or scaled unevenly"; places = null; }
					else if (places.Count == 0) why = "it is inside a block that is not placed anywhere";
				}
				if (why == null)
				{
					string path = file;
					if (!File.Exists(path)) path = Path.Combine(folder, fileName(file));
					if (!File.Exists(path)) why = "its file was not found";
					else if (!cache.TryGetValue(path, out bmp))
					{
						try
						{
							byte[] raw = loadBmp(path, maxWidth, maxHeight);
							bmp = raw == null ? null : Bitmap24.FromBmpFile(raw);
						}
						catch (Exception ex) { result.Warnings.Add(label + ": " + ex.Message); bmp = null; }
						cache[path] = bmp;
					}
					if (why == null && bmp == null) why = "the picture could not be read";
					if (why == null) file = path;
				}
				if (why != null)
				{
					result.Kept++;
					result.Messages.Add(label + " was left as a linked image: " + why);
					if (img.Definition != null) usedDefs.Add(img.Definition);
					if (!string.IsNullOrEmpty(file))
					{
						result.KeptFiles.Add(file);
						result.KeptFiles.Add(Path.Combine(folder, fileName(file)));
					}
					continue;
				}

				// rectangle of the image in its own block (insert point = lower left corner)
				double x0 = img.InsertPoint.X, y0 = img.InsertPoint.Y;
				double x1 = x0 + img.UVector.X * img.Size.X, y1 = y0 + img.VVector.Y * img.Size.Y;
				foreach (Placement p in places)
				{
					bool paper = !string.Equals(p.Space.Name, BlockRecord.ModelSpaceName, StringComparison.OrdinalIgnoreCase);
					double l = x0 * p.Scale + p.Dx, r = x1 * p.Scale + p.Dx, b = y0 * p.Scale + p.Dy, t = y1 * p.Scale + p.Dy;
					double z = img.InsertPoint.Z * p.Scale + p.Z;
					var ole = new Ole2Frame();
					ole.BinaryData = OleImage.BuildFrameData(bmp, l, b, r, t, z, paper, itemId++);
					ole.UpperLeftCorner = new XYZ(l, t, z);
					ole.LowerRightCorner = new XYZ(r, b, z);
					ole.IsPaperSpace = paper;
					ole.OleObjectType = OleObjectType.Embedded;
					ole.SourceApplication = "OLE";
					if (img.Layer != null) ole.Layer = img.Layer;
					try
					{
						ole.ExtendedData.Add("ACAD", new ExtendedData(xdata(r - l, t - b)));
					}
					catch (Exception ex) { result.Warnings.Add("xdata: " + ex.Message); }
					p.Space.Entities.Add(ole);
					result.Created++;
				}
				owner.Entities.Remove(img);
				result.Converted++;
				freed.Add(file);
			}

			if (result.Converted == 0) return result;

			// image definitions nobody shows any more
			try
			{
				foreach (ImageDefinition def in doc.ImageDefinitions.ToList())
					if (!usedDefs.Contains(def)) doc.ImageDefinitions.Remove(def.Name);
			}
			catch (Exception ex) { result.Warnings.Add("image list: " + ex.Message); }
			foreach (ImageDefinition def in usedDefs)
				if (!string.IsNullOrEmpty(def.FileName))
				{
					freed.Remove(def.FileName);
					freed.Remove(Path.Combine(folder, fileName(def.FileName)));
				}

			string target = dwgOut, temp = dwgOut + ".emperor.tmp";
			using (var writer = new DwgWriter(temp, doc))
			{
				writer.OnNotification += (s, e) => { if (e.NotificationType == NotificationType.Error) result.Warnings.Add("write: " + e.Message); };
				writer.Write();
			}
			// the new file must open again before it replaces anything
			using (var check = new DwgReader(temp)) check.Read();
			if (File.Exists(target)) File.Delete(target);
			File.Move(temp, target);
			result.Saved = true;
			result.FreedFiles.AddRange(freed);
			return result;
		}

		// Follows the inserts of a block up to the model / paper space. False = a transform that an OLE frame cannot follow.
		private static bool resolve(BlockRecord block, Placement p, Dictionary<BlockRecord, List<KeyValuePair<Insert, BlockRecord>>> uses, List<Placement> found, int depth)
		{
			if (block.Layout != null || block.Name.StartsWith("*Model_Space", StringComparison.OrdinalIgnoreCase) || block.Name.StartsWith("*Paper_Space", StringComparison.OrdinalIgnoreCase))
			{
				p.Space = block;
				found.Add(p);
				return true;
			}
			if (depth > 8) return false;
			if (!uses.TryGetValue(block, out var list)) return true;      // not placed anywhere
			XYZ basePoint = block.BlockEntity != null ? block.BlockEntity.BasePoint : XYZ.Zero;
			foreach (var use in list)
			{
				Insert ins = use.Key;
				if (ins.IsMultiple) return false;
				if (Math.Abs(ins.Rotation) > EPS) return false;
				if (Math.Abs(ins.Normal.X) > EPS || Math.Abs(ins.Normal.Y) > EPS || ins.Normal.Z <= 0) return false;
				if (ins.XScale <= 0 || Math.Abs(ins.XScale - ins.YScale) > EPS * Math.Max(1, Math.Abs(ins.XScale))) return false;
				// point q of the block -> (q - base) * s + insert point ; then the outer placement
				double s = ins.XScale;
				// inner (already accumulated) : x_block = x * p.Scale + p.Dx   ->  outer : (x_block - base) * s + ins
				var next = new Placement { Scale = p.Scale * s };
				next.Dx = (p.Dx - basePoint.X) * s + ins.InsertPoint.X;
				next.Dy = (p.Dy - basePoint.Y) * s + ins.InsertPoint.Y;
				next.Z = (p.Z - basePoint.Z) * s + ins.InsertPoint.Z;
				if (!resolve(use.Value, next, uses, found, depth + 1)) return false;
			}
			return true;
		}

		private static string fileName(string path)
		{
			int i = path.LastIndexOfAny(new[] { '\\', '/' });
			return i < 0 ? path : path.Substring(i + 1);
		}

		private static List<ExtendedDataRecord> xdata(double width, double height)
		{
			return new List<ExtendedDataRecord>
			{
				new ExtendedDataString("OLEBEGIN"),
				new ExtendedDataInteger16(70), new ExtendedDataInteger16(1),
				new ExtendedDataInteger16(71), new ExtendedDataInteger16(1),
				new ExtendedDataInteger16(40), new ExtendedDataReal(0.0),
				new ExtendedDataInteger16(41), new ExtendedDataReal(width),
				new ExtendedDataInteger16(42), new ExtendedDataReal(height),
				new ExtendedDataInteger16(72), new ExtendedDataInteger16(0),
				new ExtendedDataInteger16(3), new ExtendedDataString(""),
				new ExtendedDataInteger16(90), new ExtendedDataInteger32(0),
				new ExtendedDataInteger16(43), new ExtendedDataReal(0.0),
				new ExtendedDataInteger16(4), new ExtendedDataString(""),
				new ExtendedDataInteger16(91), new ExtendedDataInteger32(0),
				new ExtendedDataInteger16(44), new ExtendedDataReal(0.0),
				new ExtendedDataString("OLEEND"),
			};
		}
	}
}
