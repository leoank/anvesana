// SPDX-License-Identifier: GPL-2.0
/*
 * n1x-lps0: tell the firmware about suspend-to-idle on NVIDIA N1X laptops, as Windows does.
 *
 * Windows calls the Microsoft "Low Power S0 Idle" _DSM (UUID 11e00d56-ce64-47ce-837b-
 * 1f898f9aa461) on the PNP0D80 device around Modern Standby. Linux does the same only on x86
 * (drivers/acpi/x86/s2idle.c), so on this arm64 machine the firmware is never told. On the MSI
 * Prestige N16 Flip AI+ (bbaum-pc-7) the device is \_SB.PEPD (NVDA6210, _CID PNP0D80), and its
 * function 7 ("Modern Standby entry") sets bit 1 of EC byte 0xEC through WMIP and adjusts three
 * SoC registers; function 8 ("exit") clears the EC bit again. Without them the keyboard
 * backlight stays on in suspend.
 *
 * Order, as in drivers/acpi/x86/s2idle.c: before suspend, display off (3), Modern Standby
 * entry (7), sleep entry (5); after resume, sleep exit (6), Modern Standby exit (8), display on
 * (4). Each call only if function 0 lists it. Only for suspend-to-idle, not for deep sleep.
 *
 * Calls run in this driver's suspend_late / resume_early callbacks: after every device's
 * suspend (display already off), before any device's resume.
 */

#include <linux/acpi.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/suspend.h>
#include <linux/uuid.h>

#define LPS0_DISPLAY_OFF	3
#define LPS0_DISPLAY_ON		4
#define LPS0_ENTRY		5
#define LPS0_EXIT		6
#define LPS0_MS_ENTRY		7
#define LPS0_MS_EXIT		8

static const guid_t lps0_ms_guid =
	GUID_INIT(0x11e00d56, 0xce64, 0x47ce, 0x83, 0x7b, 0x1f, 0x89, 0x8f, 0x9a, 0xa4, 0x61);

static char *hid = "NVDA6210";
module_param(hid, charp, 0444);
MODULE_PARM_DESC(hid, "ACPI _HID of the PNP0D80 (LPS0) device (default NVDA6210)");

static acpi_handle lps0_handle;
static u64 lps0_mask;
static bool lps0_entered;
static struct platform_device *lps0_pdev;

static void lps0_call(struct device *dev, unsigned int fn, const char *name)
{
	union acpi_object *out;

	if (!(lps0_mask & BIT(fn)))
		return;
	out = acpi_evaluate_dsm(lps0_handle, &lps0_ms_guid, 0, fn, NULL);
	dev_info(dev, "LPS0 _DSM %u (%s): %s\n", fn, name, out ? "ok" : "no result");
	ACPI_FREE(out);
}

static int lps0_suspend_late(struct device *dev)
{
	if (pm_suspend_target_state != PM_SUSPEND_TO_IDLE)
		return 0;
	lps0_call(dev, LPS0_DISPLAY_OFF, "display off");
	lps0_call(dev, LPS0_MS_ENTRY, "modern standby entry");
	lps0_call(dev, LPS0_ENTRY, "sleep entry");
	lps0_entered = true;
	return 0;
}

static int lps0_resume_early(struct device *dev)
{
	if (!lps0_entered)
		return 0;
	lps0_call(dev, LPS0_EXIT, "sleep exit");
	lps0_call(dev, LPS0_MS_EXIT, "modern standby exit");
	lps0_call(dev, LPS0_DISPLAY_ON, "display on");
	lps0_entered = false;
	return 0;
}

static const struct dev_pm_ops lps0_pm_ops = {
	.suspend_late = lps0_suspend_late,
	.resume_early = lps0_resume_early,
};

static struct platform_driver lps0_driver = {
	.driver = {
		.name = "n1x-lps0",
		.pm = &lps0_pm_ops,
	},
};

static int __init lps0_init(void)
{
	struct acpi_device *adev;
	union acpi_object *obj;
	int ret, i;

	adev = acpi_dev_get_first_match_dev(hid, NULL, -1);
	if (!adev) {
		pr_info("n1x-lps0: no %s device\n", hid);
		return -ENODEV;
	}
	lps0_handle = adev->handle;
	acpi_dev_put(adev);

	obj = acpi_evaluate_dsm_typed(lps0_handle, &lps0_ms_guid, 0, 0, NULL, ACPI_TYPE_BUFFER);
	if (!obj) {
		pr_info("n1x-lps0: %s has no Microsoft LPS0 _DSM\n", hid);
		return -ENODEV;
	}
	for (i = 0; i < obj->buffer.length && i < 8; i++)
		lps0_mask |= (u64)obj->buffer.pointer[i] << (8 * i);
	ACPI_FREE(obj);
	if (!(lps0_mask & 1)) {
		pr_info("n1x-lps0: _DSM function 0 lists no functions (0x%llx)\n", lps0_mask);
		return -ENODEV;
	}

	ret = platform_driver_register(&lps0_driver);
	if (ret)
		return ret;
	/* Registered last, so in each suspend phase it runs first, and in each resume phase last. */
	lps0_pdev = platform_device_register_simple("n1x-lps0", PLATFORM_DEVID_NONE, NULL, 0);
	if (IS_ERR(lps0_pdev)) {
		platform_driver_unregister(&lps0_driver);
		return PTR_ERR(lps0_pdev);
	}
	pr_info("n1x-lps0: %s Microsoft LPS0 _DSM, functions 0x%llx\n", hid, lps0_mask);
	return 0;
}

static void __exit lps0_exit(void)
{
	platform_device_unregister(lps0_pdev);
	platform_driver_unregister(&lps0_driver);
}

module_init(lps0_init);
module_exit(lps0_exit);

MODULE_DESCRIPTION("Microsoft LPS0 _DSM calls around suspend-to-idle on NVIDIA N1X laptops");
MODULE_LICENSE("GPL");
