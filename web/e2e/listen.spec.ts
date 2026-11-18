import { expect, test } from "@playwright/test";

const EN = "The exit load is 1% within 1 year. Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth";
const HI = "एग्ज़िट लोड 1 वर्ष के भीतर 1% है। Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth";

test("no Hindi voice: Listen reads the English answer at once and keeps speaking", async ({ page }) => {
  // A device with only an English voice; record every speechSynthesis call in order.
  await page.addInitScript(() => {
    const log: string[] = [];
    (window as unknown as { __speech: string[] }).__speech = log;
    const voices = [{ lang: "en-IN", name: "Rishi", default: true, localService: true, voiceURI: "Rishi" }];
    class FakeUtterance {
      lang = ""; voice: unknown = null; onend: (() => void) | null = null; onerror: (() => void) | null = null;
      constructor(public text: string) {}
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: FakeUtterance });
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        getVoices: () => voices,
        speak: (u: { lang: string; text: string }) => log.push(`speak:${u.lang}:${u.text.slice(0, 20)}`),
        cancel: () => log.push("cancel"),
        addEventListener() {},
        removeEventListener() {},
      },
    });
  });
  await page.route("**/api/tickets/GRW-HINDI1", (route) =>
    route.fulfill({
      json: {
        code: "GRW-HINDI1", status: "answered", question: "HDFC mid cap ka exit load kitna hai", answer: EN,
        answer_local: { language: "hi", text: HI }, answered_at: "2026-11-18T10:00:00Z", language: "hinglish",
        intent: "fee_question",
      },
    }));
  await page.goto("/t/GRW-HINDI1");
  await expect(page.getByRole("region", { name: "Answer" })).toContainText("एग्ज़िट");
  await page.getByRole("button", { name: /Listen/ }).click();
  await expect(page.getByText("No Hindi voice on this device — reading in English.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Answer" })).toContainText("The exit load is 1%");
  await page.waitForTimeout(300);
  const log = await page.evaluate(() => (window as unknown as { __speech: string[] }).__speech);
  const spoke = log.findIndex((l) => l.startsWith("speak:en-IN:The exit load"));
  expect(spoke).toBeGreaterThanOrEqual(0);
  expect(log.slice(spoke + 1)).not.toContain("cancel");   // nothing cuts the English reading off
  await expect(page.getByRole("button", { name: /Stop/ })).toBeVisible();
});
