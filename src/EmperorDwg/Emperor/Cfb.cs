// Emperor - minimal writer for a Compound File (OLE structured storage, version 3, 512-byte sectors).
// Only what an embedded OLE object needs: a root storage with a few streams.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace EmperorDwg
{
	internal sealed class CfbStream
	{
		public string Name;
		public byte[] Data;
		public CfbStream(string name, byte[] data) { this.Name = name; this.Data = data; }
	}

	internal static class Cfb
	{
		private const uint FREE = 0xFFFFFFFF, EOC = 0xFFFFFFFE, FATSECT = 0xFFFFFFFD, DIFSECT = 0xFFFFFFFC, NOSTREAM = 0xFFFFFFFF;
		private const int SEC = 512, MINI = 64, CUTOFF = 4096;

		private static int compare(string a, string b)
		{
			if (a.Length != b.Length) return a.Length.CompareTo(b.Length);
			return string.CompareOrdinal(a.ToUpperInvariant(), b.ToUpperInvariant());
		}

		/// <summary>Builds the compound file. streams: name -> data. rootClsid: class of the embedded object.</summary>
		public static byte[] Build(Guid rootClsid, List<CfbStream> streams)
		{
			streams = new List<CfbStream>(streams);
			streams.Sort((x, y) => compare(x.Name, y.Name));
			int n = streams.Count;

			// ---- mini stream (streams below the cutoff)
			var mini = new MemoryStream();
			var miniFat = new List<uint>();
			uint[] start = new uint[n];
			for (int i = 0; i < n; i++)
			{
				byte[] d = streams[i].Data;
				if (d.Length >= CUTOFF || d.Length == 0) continue;
				int first = miniFat.Count, count = (d.Length + MINI - 1) / MINI;
				for (int k = 0; k < count; k++) miniFat.Add(k == count - 1 ? EOC : (uint)(first + k + 1));
				start[i] = (uint)first;
				mini.Write(d, 0, d.Length);
				int pad = count * MINI - d.Length;
				if (pad > 0) mini.Write(new byte[pad], 0, pad);
			}
			byte[] miniData = mini.ToArray();

			// ---- sector plan (regular sectors, numbered after the header)
			int dirSectors = (n + 1 + 3) / 4;                       // 4 directory entries per sector
			int miniFatSectors = (miniFat.Count + 127) / 128;
			int miniDataSectors = (miniData.Length + SEC - 1) / SEC;
			int[] bigSectors = new int[n];
			int dataSectors = 0;
			for (int i = 0; i < n; i++)
				if (streams[i].Data.Length >= CUTOFF) { bigSectors[i] = (streams[i].Data.Length + SEC - 1) / SEC; dataSectors += bigSectors[i]; }
			int content = dirSectors + miniFatSectors + miniDataSectors + dataSectors;
			int fatSectors = 0, difSectors = 0;
			while (true)
			{
				int total = content + fatSectors + difSectors;
				int needFat = (total + 127) / 128;
				int needDif = needFat <= 109 ? 0 : (needFat - 109 + 126) / 127;
				if (needFat == fatSectors && needDif == difSectors) break;
				fatSectors = needFat; difSectors = needDif;
			}
			int totalSectors = content + fatSectors + difSectors;
			uint[] fat = new uint[fatSectors * 128];
			for (int i = 0; i < fat.Length; i++) fat[i] = FREE;

			int next = 0;
			int fatStart = next; next += fatSectors;
			for (int i = 0; i < fatSectors; i++) fat[fatStart + i] = FATSECT;
			int difStart = next; next += difSectors;
			for (int i = 0; i < difSectors; i++) fat[difStart + i] = DIFSECT;
			int dirStart = next; next += dirSectors;
			chain(fat, dirStart, dirSectors);
			int miniFatStart = next; next += miniFatSectors;
			chain(fat, miniFatStart, miniFatSectors);
			int miniDataStart = next; next += miniDataSectors;
			chain(fat, miniDataStart, miniDataSectors);
			for (int i = 0; i < n; i++)
			{
				if (bigSectors[i] == 0) continue;
				start[i] = (uint)next;
				chain(fat, next, bigSectors[i]);
				next += bigSectors[i];
			}

			var ms = new MemoryStream(SEC * (totalSectors + 1));
			var w = new BinaryWriter(ms);

			// ---- header
			w.Write(new byte[] { 0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1 });
			w.Write(new byte[16]);
			w.Write((ushort)0x003E); w.Write((ushort)0x0003); w.Write((ushort)0xFFFE);
			w.Write((ushort)9); w.Write((ushort)6);
			w.Write(new byte[6]);
			w.Write((uint)0);                                  // directory sectors (0 in version 3)
			w.Write((uint)fatSectors);
			w.Write((uint)dirStart);
			w.Write((uint)0);
			w.Write((uint)CUTOFF);
			w.Write(miniFatSectors > 0 ? (uint)miniFatStart : EOC);
			w.Write((uint)miniFatSectors);
			w.Write(difSectors > 0 ? (uint)difStart : EOC);
			w.Write((uint)difSectors);
			for (int i = 0; i < 109; i++) w.Write(i < fatSectors ? (uint)(fatStart + i) : FREE);

			// ---- FAT
			foreach (uint v in fat) w.Write(v);
			// ---- DIFAT sectors
			int fi = 109;
			for (int s = 0; s < difSectors; s++)
			{
				for (int k = 0; k < 127; k++) { w.Write(fi < fatSectors ? (uint)(fatStart + fi) : FREE); fi++; }
				w.Write(s == difSectors - 1 ? EOC : (uint)(difStart + s + 1));
			}

			// ---- directory: entry 0 = root, entries 1..n = streams (sorted), balanced binary tree
			uint[] left = new uint[n + 1], right = new uint[n + 1];
			for (int i = 0; i <= n; i++) { left[i] = NOSTREAM; right[i] = NOSTREAM; }
			int[] depth = new int[n + 1];
			uint rootChild = n > 0 ? (uint)(tree(0, n - 1, left, right, depth, 1) + 1) : NOSTREAM;
			int maxDepth = 0;
			foreach (int dd in depth) maxDepth = Math.Max(maxDepth, dd);
			bool perfect = n == (1 << maxDepth) - 1;
			writeEntry(w, "Root Entry", 5, NOSTREAM, NOSTREAM, rootChild, rootClsid, miniDataSectors > 0 ? (uint)miniDataStart : EOC, (uint)miniData.Length);
			for (int i = 0; i < n; i++)
			{
				int len = streams[i].Data.Length;
				// red-black colours: the deepest (incomplete) level is red, everything else black
				byte colour = (byte)(!perfect && depth[i + 1] == maxDepth ? 0 : 1);
				writeEntry(w, streams[i].Name, 2, left[i + 1], right[i + 1], NOSTREAM, Guid.Empty, len == 0 ? EOC : start[i], (uint)len, colour);
			}
			for (int i = n + 1; i < dirSectors * 4; i++) writeEntry(w, "", 0, NOSTREAM, NOSTREAM, NOSTREAM, Guid.Empty, 0, 0);

			// ---- mini FAT, mini stream, big streams
			for (int i = 0; i < miniFatSectors * 128; i++) w.Write(i < miniFat.Count ? miniFat[i] : FREE);
			w.Write(miniData); pad(w);
			for (int i = 0; i < n; i++)
			{
				if (bigSectors[i] == 0) continue;
				w.Write(streams[i].Data); pad(w);
			}
			w.Flush();
			return ms.ToArray();
		}

		private static int tree(int lo, int hi, uint[] left, uint[] right, int[] depth, int level)
		{
			int mid = (lo + hi + 1) / 2;
			depth[mid + 1] = level;
			if (lo < mid) left[mid + 1] = (uint)(tree(lo, mid - 1, left, right, depth, level + 1) + 1);
			if (mid < hi) right[mid + 1] = (uint)(tree(mid + 1, hi, left, right, depth, level + 1) + 1);
			return mid;
		}

		private static void chain(uint[] fat, int first, int count)
		{
			for (int i = 0; i < count; i++) fat[first + i] = i == count - 1 ? EOC : (uint)(first + i + 1);
		}

		private static void pad(BinaryWriter w)
		{
			long r = w.BaseStream.Position % SEC;
			if (r != 0) w.Write(new byte[SEC - r]);
		}

		private static void writeEntry(BinaryWriter w, string name, byte type, uint left, uint right, uint child, Guid clsid, uint start, uint size, byte colour = 1)
		{
			byte[] nm = new byte[64];
			byte[] raw = Encoding.Unicode.GetBytes(name);
			Array.Copy(raw, nm, Math.Min(raw.Length, 62));
			w.Write(nm);
			w.Write((ushort)(type == 0 ? 0 : raw.Length + 2));
			w.Write(type);
			w.Write(colour);
			w.Write(left); w.Write(right); w.Write(child);
			w.Write(clsid.ToByteArray());
			w.Write((uint)0);
			w.Write((long)0); w.Write((long)0);
			w.Write(start);
			w.Write(size); w.Write((uint)0);
		}
	}
}
