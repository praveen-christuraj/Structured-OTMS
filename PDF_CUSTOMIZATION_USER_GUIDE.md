# PDF Customization Quick Reference Guide

## 🚀 Quick Start

### Step 1: Open PDF Customization
1. Navigate to **Dashboard Customization** → **📄 PDF Customization** tab
2. You'll see the interactive canvas and configuration options

### Step 2: Configure Page Settings
```
Page Size:      A4 (default), A3, Letter, or Legal
Orientation:    Portrait or Landscape
Grid Columns:   2-12 (default: 12)
```

### Step 3: Add Widgets
1. Select widget type from dropdown (Summary Cards, Tank Visuals, Monthly Data, Trend Chart)
2. Choose location (Top, Center, Bottom)
3. Click "Add to Canvas"

### Step 4: Arrange Widgets in Canvas

#### Moving Widgets
- **Click and drag** any widget to reposition
- Widgets snap to grid for alignment
- Position shown in real-time

#### Resizing Widgets
- **Drag the corner handles** (↖️ ↗️ ↙️ ↘️) to resize
- **Drag edge midpoints** (↕️ ↔️) to resize in one direction
- Minimum size: 1×1 grid cell
- Maximum size: Grid width × unlimited height

#### Quick Positions
- Use **↖️ Top Left**, **↗️ Top Right**, **↙️ Bottom Left**, **↘️ Bottom Right** buttons
- Automatically positions widget at specified corner

### Step 5: Select Display Type

#### For Each Widget:
Choose **📋 Table** or **📊 Visual**

**Table Mode:**
- Traditional tabular data layout
- Detailed numerical values
- Best for: Raw data analysis

**Visual Mode:**
- Color-coded and enhanced formatting
- Visual indicators (↑↓→ trends, ■ fill bars)
- Better for: Executive summaries, presentations

### Step 6: Export PDF
1. Click **📥 Export Dashboard as PDF** button
2. PDF opens automatically in new tab
3. Layout matches canvas configuration
4. Display types applied (table or visual)

---

## 🎨 Canvas Reference

### Widget Colors (Visual Mode)
- 🔵 Blue: Summary Cards
- 🟢 Green: Tank Visuals
- 🟡 Amber: Monthly Data
- 🔴 Red/Purple/Cyan: Additional metrics

### Resize Handles
```
    ↖️ TL ─ ↕️ TM ─ ↗️ TR
    ↔️  [  WIDGET  ]  ↔️
    ↙️ BL ─ ↕️ BM ─ ↘️ BR
```

### Grid Reference
- **Columns**: X-axis position (0 to max_columns-1)
- **Rows**: Y-axis position (0 to unlimited)
- **Width**: Grid cell count horizontally
- **Height**: Grid cell count vertically

---

## 📊 Widget Type Guide

### Summary Cards
**Table Mode:** Shows metrics in rows
- Name | Value | Unit

**Visual Mode:** Color-coded metric display
- Larger fonts, centered
- Background colors by metric
- Better spacing

### Tank Visuals
**Table Mode:** Tank data table
- Tank Name | Current | Fill %

**Visual Mode:** Tank visuals with indicators
- Fill percentage display (65%)
- Visual bar (■■■■■■)
- Color-coded background

### Monthly Data
**Table Mode:** Monthly totals
- Visual | Total

**Visual Mode:** Extended metrics
- Visual | Total | Average
- Green background for emphasis

### Trend Chart
**Table Mode:** Series data
- Series | Total

**Visual Mode:** Series with trend indicators
- Series | Total | Trend
- Shows ↑ Increasing, ↓ Decreasing, → Stable

---

## 💡 Tips & Tricks

### Layout Design
1. **Start wide**: Use larger widgets first
2. **Fill gaps**: Add smaller widgets to gaps
3. **Group by type**: Place similar widgets together
4. **Balance**: Distribute widgets evenly

### Performance
- More widgets = larger PDF file
- Limit to 8-12 widgets per page for best results
- Use multiple exports if needed

### Display Type Selection
- **Table** for detailed analysis
- **Visual** for management presentations
- Mix modes for flexibility (e.g., Cards as Visual, Charts as Table)

### Troubleshooting

**Widget won't move?**
- Click and drag the widget center
- Ensure it's not beyond canvas boundaries

**Text overlapping?**
- Increase widget height
- Reduce grid columns for wider cells

**PDF looks different from preview?**
- Grid columns affect PDF layout
- Page size affects spacing
- Reload page if changes don't appear

---

## 🔧 Configuration Details

### Page Sizes
```
A4      (210×297mm) - Standard office document
A3      (297×420mm) - Large format
Letter  (8.5×11")   - US standard
Legal   (8.5×14")   - US legal size
```

### Grid Columns Impact
```
2 cols   = Very wide widgets (best for 1-2 items)
4 cols   = Large widgets (2-3 items per row)
6 cols   = Medium widgets (2 items side-by-side)
12 cols  = Small widgets (many items per row)
```

### Recommended Layouts

**Executive Dashboard (A3 Landscape, 12 cols):**
- 3 Summary Cards (width 4 each)
- 1 Tank Visual (width 6)
- 1 Trend Chart (width 6)

**Department Report (A4 Portrait, 6 cols):**
- 2 Summary Cards (width 3 each)
- 1 Monthly Data (width 6)
- 1 Trend Chart (width 6)

**Analytics Sheet (A3 Landscape, 4 cols):**
- 1 Summary Card (width 4)
- 1 Tank Visual (width 4)
- 1 Monthly Data (width 4)
- 1 Trend Chart (width 4)

---

## 📝 Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Delete Widget | Click 🗑️ button |
| Quick Positions | Click ↖️ ↗️ ↙️ ↘️ |
| Change Display | Click 📋 or 📊 |

---

## ❓ FAQ

**Q: Can I save my layout?**
A: Yes! Configuration is auto-saved when you add/move widgets.

**Q: Can I export same layout multiple times?**
A: Yes! Use the Export button to generate as many PDFs as needed.

**Q: Can I use both table and visual in same PDF?**
A: Yes! Select different display types for each widget.

**Q: What's the max number of widgets?**
A: Unlimited, but recommend 8-12 for readability.

**Q: Can I undo changes?**
A: Refresh page to revert to last saved state.

**Q: Are my settings saved?**
A: Yes, in dashboard configuration automatically.

---

## 🆘 Support

**Issue:** Widgets disappear after refresh
- Check browser console for errors
- Verify configuration file exists
- Try clearing browser cache

**Issue:** PDF export fails
- Check location/date range settings
- Verify data exists in database
- Ensure all widgets have valid configuration

**Issue:** Display type not applying
- Reload page after changing display type
- Try selecting it again
- Clear browser cache if persistent

---

*Last Updated: 2024*
*For support, contact your system administrator*
