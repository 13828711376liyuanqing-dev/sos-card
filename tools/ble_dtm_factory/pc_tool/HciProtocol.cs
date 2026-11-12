// SAM | 2026-10-10 22:48 +08:00 | Add isolated HCI H4 DTM framing because the factory PC must control GR5526 without changing the CAT1 tool.
using System;
using System.Collections.Generic;

namespace Yp001BleDtm
{
    public sealed class HciEvent
    {
        public byte Code;
        public byte[] Parameters;
        public byte[] Raw;

        public bool IsCommandComplete(ushort opcode)
        {
            return Code == 0x0E && Parameters.Length >= 4 &&
                   (ushort)(Parameters[1] | (Parameters[2] << 8)) == opcode;
        }

        public byte Status { get { return Parameters.Length >= 4 ? Parameters[3] : (byte)0xFF; } }
        public int ReceivedPackets
        {
            get
            {
                return Parameters.Length >= 6 ? Parameters[4] | (Parameters[5] << 8) : -1;
            }
        }
    }

    public sealed class HciParser
    {
        private readonly List<byte> buffer = new List<byte>();

        public List<HciEvent> Feed(byte[] data, int count)
        {
            if (data == null || count < 0 || count > data.Length) throw new ArgumentException("Invalid HCI chunk");
            for (int i = 0; i < count; i++) buffer.Add(data[i]);
            List<HciEvent> events = new List<HciEvent>();
            while (buffer.Count > 0)
            {
                if (buffer[0] != 0x04) { buffer.RemoveAt(0); continue; }
                if (buffer.Count < 3) break;
                int size = 3 + buffer[2];
                if (buffer.Count < size) break;
                byte[] raw = buffer.GetRange(0, size).ToArray();
                byte[] parameters = new byte[size - 3];
                Array.Copy(raw, 3, parameters, 0, parameters.Length);
                events.Add(new HciEvent { Code = raw[1], Parameters = parameters, Raw = raw });
                buffer.RemoveRange(0, size);
            }
            return events;
        }

        public void Clear() { buffer.Clear(); }
    }

    public static class HciCommands
    {
        public const ushort ResetOpcode = 0x0C03;
        public const ushort ReceiverTestOpcode = 0x201D;
        public const ushort TransmitterTestOpcode = 0x201E;
        public const ushort TestEndOpcode = 0x201F;

        public static byte[] Reset() { return Command(ResetOpcode); }
        public static byte[] ReceiverTest(int channel)
        {
            CheckChannel(channel);
            return Command(ReceiverTestOpcode, (byte)channel);
        }
        public static byte[] TransmitterTest(int channel, int length)
        {
            CheckChannel(channel);
            if (length < 0 || length > 37) throw new ArgumentOutOfRangeException("length");
            return Command(TransmitterTestOpcode, (byte)channel, (byte)length, 0x00); // PRBS9
        }
        public static byte[] TestEnd() { return Command(TestEndOpcode); }

        private static void CheckChannel(int channel)
        {
            if (channel < 0 || channel > 39) throw new ArgumentOutOfRangeException("channel");
        }
        private static byte[] Command(ushort opcode, params byte[] parameters)
        {
            byte[] frame = new byte[4 + parameters.Length];
            frame[0] = 0x01; // HCI H4 command packet
            frame[1] = (byte)(opcode & 0xFF);
            frame[2] = (byte)(opcode >> 8);
            frame[3] = (byte)parameters.Length;
            Array.Copy(parameters, 0, frame, 4, parameters.Length);
            return frame;
        }
        public static string Hex(byte[] data)
        {
            return BitConverter.ToString(data).Replace("-", " ");
        }
    }
}
