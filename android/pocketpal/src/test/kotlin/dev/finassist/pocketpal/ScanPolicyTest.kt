package dev.finassist.pocketpal

import org.junit.Assert.*
import org.junit.Test

class ScanPolicyTest {
    @Test fun captureWindowIsStrictAndNeverSubstitutesImportTime() {
        val now = 2_000_000_000_000L
        assertTrue(ScanPolicy.recent(now, now))
        assertTrue(ScanPolicy.recent(now - ScanPolicy.WINDOW_MS, now))
        assertFalse(ScanPolicy.recent(now - ScanPolicy.WINDOW_MS - 1, now))
        assertFalse(ScanPolicy.recent(now + 1, now))
        assertFalse(ScanPolicy.recent(0, now))
        assertFalse(ScanPolicy.recent(-1, now))
    }
    @Test fun candidateRequiresTransactionAndCurrencyEvidenceAndDecimal() {
        assertTrue(ScanPolicy.candidate("PAYMENT COMPLETED Amount 120.00 Baht"))
        assertTrue(ScanPolicy.candidate("Transaction Reference ABC123 total THB 1,200.50"))
        assertFalse(ScanPolicy.candidate("Holiday photo 120.00"))
        assertFalse(ScanPolicy.candidate("Bank branch opening hours 09:00"))
        assertFalse(ScanPolicy.candidate("Transfer successful"))
        // Honest known limitations: generic ad can pass; Thai words alone (no slip layout) do not match.
        assertTrue(ScanPolicy.candidate("Payment service ad amount 120.00 baht"))
        assertFalse(ScanPolicy.candidate("โอนเงินสำเร็จ จำนวน 120.00 บาท"))
    }
    @Test fun oversizedImageReadStopsAtTheBoundary() {
        val input = java.io.ByteArrayInputStream(ByteArray(ScanPolicy.MAX_BYTES + 100))
        assertEquals(ScanPolicy.MAX_BYTES + 1, ScanPolicy.readBounded(input).size)
        assertEquals(99, input.available())
    }
    @Test fun uploadAttemptsAndLocalScanWorkAreBounded() {
        assertTrue(ScanPolicy.mayAttempt(99, 9, 19))
        assertFalse(ScanPolicy.mayAttempt(100, 0, 0))
        assertFalse(ScanPolicy.mayAttempt(0, 10, 0))
        assertFalse(ScanPolicy.mayAttempt(0, 0, 20))
    }

    @Test fun censusClassifiesCaptureDatesWithoutSubstitutingImportTime() {
        val now = 2_000_000_000_000L
        assertEquals(ScanPolicy.DateClass.UNDATED, ScanPolicy.dateClass(null, now))
        assertEquals(ScanPolicy.DateClass.UNDATED, ScanPolicy.dateClass(0, now))
        assertEquals(ScanPolicy.DateClass.FUTURE, ScanPolicy.dateClass(now + 1, now))
        assertEquals(ScanPolicy.DateClass.OLDER, ScanPolicy.dateClass(now - ScanPolicy.WINDOW_MS - 1, now))
        assertEquals(ScanPolicy.DateClass.IN_WINDOW, ScanPolicy.dateClass(now - ScanPolicy.WINDOW_MS, now))
        assertEquals(ScanPolicy.DateClass.IN_WINDOW, ScanPolicy.dateClass(now, now))
    }
    @Test fun layoutRuleMatchesThaiSlipDigitsReadByLatinModel() {
        // Synthetic text only. The Latin recognizer drops Thai words but keeps digits, masks and times.
        assertTrue(ScanPolicy.candidate("17 Oct. 2569 09:05\nxxx-x-x1234-x\n1,250.00\n016290090512AQR07123"))
        assertTrue(ScanPolicy.candidate("120.00\nXXX-X-X5678-X\n12:41"))
        assertTrue(ScanPolicy.candidate("350.50 202610171234567890 2569"))
        assertEquals(2, ScanPolicy.FILTER_VERSION)
    }
    @Test fun layoutRuleNeedsAllThreeKindsOfEvidence() {
        assertFalse(ScanPolicy.candidate("Menu 120.00 89.50 open 10:00"))            // amount + time, no account/reference
        assertFalse(ScanPolicy.candidate("Receipt 120.00 xxx-x-x1234"))              // amount + mask, no time/year
        assertFalse(ScanPolicy.candidate("xxx-x-x1234 09:05 202610171234567890"))   // no amount with satang
        assertFalse(ScanPolicy.candidate("Phone 0812345678 at 18:30 price 99.00"))   // 10-digit phone is not a reference
        assertFalse(ScanPolicy.candidate("Sunset at the beach 2026"))
        assertFalse(ScanPolicy.candidate("Total 12.50 xxx-x-x1234"))                // an amount is not a time
        assertFalse(ScanPolicy.candidate("2569.00 xxx-x-x1234"))                    // an amount is not a BE year
        assertFalse(ScanPolicy.hasReference("ABCDEFGHIJKL12"))
        assertTrue(ScanPolicy.hasReference("016290090512AQR07123"))
    }
    @Test fun moneyOnlyIsACounterNotAMatch() {
        assertTrue(ScanPolicy.moneyOnly("Holiday photo 120.00"))
        assertFalse(ScanPolicy.moneyOnly("PAYMENT COMPLETED Amount 120.00 Baht"))
        assertFalse(ScanPolicy.moneyOnly("No amount here"))
    }
}
