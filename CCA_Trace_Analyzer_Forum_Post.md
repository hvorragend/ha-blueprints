# 🔍 Introducing: CCA Trace Analyzer - Debug Your Automation Instantly!

Hey everyone! 👋

I'm excited to introduce **CCA Trace Analyzer** – a powerful new debugging tool that makes understanding what happened in your Cover Control Automation automations super easy!

## ⚡ What is the Trace Analyzer?

The Trace Analyzer is a **web-based debugging tool** that takes your Home Assistant automation trace and shows you exactly what happened, step by step:

- 📊 **Visual execution path** - See every condition and action that ran
- 🎯 **Last step analysis** - Understand why execution stopped where it did
- 📋 **Helper status snapshot** - See what CCA knew at trigger time
- 📈 **Variable inspection** - Check all values during execution
- 🔍 **Instant feedback** - No waiting, no logs to parse, no confusion

## 🎯 Why Do You Need This?

When something doesn't work as expected, debugging CCA automations can be frustrating:

❌ **Without Trace Analyzer:**
- Parse Home Assistant trace JSON manually
- Dig through 50+ pages of automation logs
- Wonder why a specific branch didn't execute
- Guess which condition failed

✅ **With Trace Analyzer:**
- Upload trace JSON
- Get instant visual breakdown
- See exactly which condition blocked execution
- Understand the helper state
- Get actionable debugging tips

## 🚀 How to Use It

### Step 1: Download Your Trace
1. Go to **Settings → Automations & Scenes**
2. Click your CCA automation
3. Go to **Traces** tab
4. Select the failing trace
5. Click ⋮ menu → **Download trace**

### Step 2: Analyze
1. Open **[CCA Trace Analyzer](https://hvorragend.github.io/ha-blueprints/trace-analyzer/)**
2. Drop your trace JSON file
3. Get instant analysis! 🎉

That's it! 

## ✨ Key Features

### 📈 Execution Summary
- Status (finished/stopped)
- Trigger info with explanation
- Which branch executed
- Execution duration

### 🎯 Last Step Analysis
- What happened at the very last step
- Why the automation stopped there
- Actionable debugging suggestions

### 🦮 Helper Status Snapshot
Shows the state of your CCA helper at trigger time:
- ✅ Which positions are active
- ❌ Which positions are inactive
- When helper was last updated

### 📍 Execution Path
- Complete step-by-step trace
- Filter by conditions, actions, or failures
- Shows results and timing
- Highlights the last step

### 📊 Variable Inspector
Organized by category:
- Cover & Position settings
- Features enabled/disabled
- Time configuration
- Helper status
- Shading parameters
- And much more!

### 📤 Export & Share
- Copy analysis as text report
- Download as file
- Share with support team

## 💡 Real-World Example

**Problem:** "My cover doesn't shade during the day"

**With Trace Analyzer:**
1. Download trace when it should have shaded
2. Open analyzer
3. Immediately see:
   - "Shading Start Pending" condition evaluated
   - Sun azimuth check: ❌ FAILED (95° not in range 120-240°)
   - That's why shading didn't start!

**Solution:** Adjust azimuth threshold from 120-240° to 80-280°

Takes 2 minutes instead of 30 minutes debugging! ⏱️

## 🔒 Privacy First

- **100% client-side** - No data sent to servers
- **Works offline** - After initial load
- **No tracking** - Your traces stay on your device
- **Open source** - Code available on GitHub

## 📚 Where to Find It

**Direct Link:**
🔗 [https://hvorragend.github.io/ha-blueprints/trace-analyzer/](https://hvorragend.github.io/ha-blueprints/trace-analyzer/)

**Also available from:**
- CCA Blueprint description
- CCA README
- CCA FAQ (Troubleshooting section)
- Root README

## 🎓 Recommended Resources

When debugging, also check:
- 📋 **Configuration Validator** - Find configuration errors before deployment
  - [https://hvorragend.github.io/ha-blueprints/validator/](https://hvorragend.github.io/ha-blueprints/validator/)
- ❓ **FAQ & Troubleshooting** - Answers to common questions
  - [FAQ.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/FAQ.md)
- 📊 **Time Control Visualization** - Understand time windows
  - [TIME_CONTROL_VISUALIZATION.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/TIME_CONTROL_VISUALIZATION.md)
- ☀️ **Dynamic Sun Elevation** - Seasonal adaptation guide
  - [DYNAMIC_SUN_ELEVATION.md](https://github.com/hvorragend/ha-blueprints/blob/main/blueprints/automation/DYNAMIC_SUN_ELEVATION.md)

## 📝 Tips for Better Debugging

1. **Download the right trace**
   - Choose a trace from when the problem occurred
   - Not an unrelated successful run

2. **Understand the last step**
   - The last step shows where execution stopped
   - That's usually your debugging clue

3. **Check helper status**
   - Verify helper has expected values
   - Manual override might be blocking automation

4. **Look at conditions first**
   - Red X = failed condition
   - That's usually the culprit

5. **Check variable values**
   - Are thresholds what you expect?
   - Is sensor data available?

## 🤝 When Requesting Support

If you're stuck, the Trace Analyzer makes it super easy to get help:

1. **Use the Trace Analyzer** to narrow down the issue
2. **Share what you learned** - "Shading condition failed because azimuth is 95° but threshold is 120-240°"
3. **Include your trace** (optional, but helpful)

The team can help much faster when you've already done the analysis! ⚡

## 🎉 What's Next?

I'm always working on improvements. If you have suggestions:
- **Feature requests:** [GitHub Issues](https://github.com/hvorragend/ha-blueprints/issues)
- **Bug reports:** [GitHub Issues](https://github.com/hvorragend/ha-blueprints/issues)
- **Questions:** Reply in this thread!

## ❤️ Support the Project

If you find the Trace Analyzer (and CCA) helpful:
- 🙏 [PayPal Donation](https://www.paypal.com/donate/?hosted_button_id=NQE5MFJXAA8BQ)
- ☕ [Buy me a Coffee](https://buymeacoffee.com/herr.vorragend)

Even just sharing feedback in this thread helps! 

---

**Happy debugging!** 🔍✨

---

## Questions?

Reply below with any questions about how to use the Trace Analyzer or how it can help you debug your CCA automation!
