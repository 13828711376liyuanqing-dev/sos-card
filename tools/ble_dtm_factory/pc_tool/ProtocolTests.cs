// SAM | 2026-10-10 22:48 +08:00 | Verify exact DTM HCI packets and split RX parsing because firmware ACKs must not be guessed from UART TX success.
using System;
using Yp001BleDtm;

class ProtocolTests
{
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static void Main()
    {
        Check(HciCommands.Hex(HciCommands.Reset()) == "01 03 0C 00", "reset frame");
        Check(HciCommands.Hex(HciCommands.TransmitterTest(19, 37)) == "01 1E 20 03 13 25 00", "TX frame");
        Check(HciCommands.Hex(HciCommands.ReceiverTest(0)) == "01 1D 20 01 00", "RX frame");
        Check(HciCommands.Hex(HciCommands.TestEnd()) == "01 1F 20 00", "END frame");
        HciParser parser = new HciParser();
        byte[] a = { 0x00, 0x04, 0x0E, 0x06, 0x01, 0x1F };
        byte[] b = { 0x20, 0x00, 0xD2, 0x04 };
        Check(parser.Feed(a, a.Length).Count == 0, "split first half");
        var events = parser.Feed(b, b.Length);
        Check(events.Count == 1, "split second half");
        Check(events[0].IsCommandComplete(HciCommands.TestEndOpcode), "END ACK opcode");
        Check(events[0].Status == 0 && events[0].ReceivedPackets == 1234, "END packet count");
        byte[] failed = { 0x04, 0x0E, 0x04, 0x01, 0x1E, 0x20, 0x01 };
        Check(parser.Feed(failed, failed.Length)[0].Status == 1, "failure status preserved");
        bool range = false;
        try { HciCommands.ReceiverTest(40); } catch (ArgumentOutOfRangeException) { range = true; }
        Check(range, "channel range");
        Console.WriteLine("HCI protocol tests PASS");
    }
}
