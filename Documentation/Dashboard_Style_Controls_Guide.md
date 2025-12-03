# Dashboard Style Controls Guide

## Overview
The Dashboard Customization page now provides comprehensive control over fonts, colors, and styling for all dashboard elements.

## What Was Fixed

### Problem
Font sizes and colors configured in the Dashboard Customization → Styles tab were not being applied to dashboard widgets. The issue was:
1. **Mismatch between saved config and rendering code**: Customization UI saved styles as nested objects (`styles.value.font_size`, `styles.label.color`), but the renderer expected flat keys (`value_size`, `label_color`)
2. **Missing style options**: No controls for section headings or table styles

### Solution
1. **Updated `render_stat_card` method** to read from both nested (new) and flat (backwards compat) style structures
2. **Added new style controls** for:
   - Section headings (font size, weight, color)
   - Tables/dataframes (font size, header background)
3. **Applied styles consistently** across all dashboard sections

## Style Controls Available

### 1. Card Styles
Controls the appearance of metric/stat cards:
- **Background Color**: Card background (#ffffff default)
- **Border Radius**: Rounded corners (10px default)
- **Border Color**: Left border accent color (#667eea default)
- **Border Width**: Thickness of accent border (4px default)
- **Padding**: Inner spacing (1rem default)
- **Box Shadow**: Drop shadow effect
- **Width**: Fixed width in pixels (0 = auto)
- **Height**: Minimum height in pixels (0 = auto)

### 2. Value Text Styles
Controls the large metric values in cards:
- **Font Size**: Size in rem units (1.6 default = large)
  - Range: 0.5rem to 5.0rem
  - Step: 0.1rem
- **Font Weight**: normal, bold, bolder, lighter
- **Color**: Text color (#667eea default)

### 3. Label Text Styles
Controls the small labels above values in cards:
- **Font Size**: Size in rem units (0.8 default = small)
  - Range: 0.5rem to 3.0rem
  - Step: 0.1rem
- **Font Weight**: normal, bold, bolder, lighter
- **Color**: Text color (#666666 default)
- **Text Transform**: none, uppercase, lowercase, capitalize

### 4. Section Heading Styles ✨ NEW
Controls dashboard section headers (### headings):
- **Font Size**: Size in rem units (1.5 default)
  - Range: 0.8rem to 3.0rem
  - Step: 0.1rem
- **Font Weight**: normal, bold, bolder
- **Color**: Text color (#333333 default)

### 5. Table & Dataframe Styles ✨ NEW
Controls appearance of tables/dataframes:
- **Font Size**: Text size in rem units (0.9 default)
  - Range: 0.6rem to 2.0rem
  - Step: 0.1rem
- **Header Background**: Table header background color (#f8f9fa default)

## Where Styles Are Applied

### Stat Cards
- All summary statistic cards
- Monthly data cards
- Trend chart total cards
- Custom metric cards

### Section Headers
- "📊 Summary Statistics"
- "🛢️ Tank Stock Levels"
- "📊 Monthly Data"
- "📈 Production & Evacuation Trend"
- "⛴️ YADE Convoy Status"
- "🛳️ Vessel Convoy Status"
- Status group headers (e.g., "📋 At Jetty", "📋 Loading")

### Tables & Dataframes
- Convoy Status tables (YADE and Vessel)
- Total stock displays
- Custom data tables

## How to Use

### Step 1: Navigate to Dashboard Customization
1. Go to Dashboard Customization page from sidebar
2. Select your location
3. Click on the **"🎨 Styles"** tab

### Step 2: Adjust Styles
1. **Card Styles**: Modify background, borders, padding
2. **Value Styles**: Change metric number size and color
3. **Label Styles**: Adjust label text appearance
4. **Heading Styles**: Control section header appearance
5. **Table Styles**: Set table font size and colors

### Step 3: Save and Preview
1. Click **"💾 Save Configuration"** at the bottom of the Styles tab
2. Navigate to Home dashboard to see changes
3. All changes apply immediately after save

## Testing Checklist

### Visual Elements to Test
- [ ] Summary stat cards show correct font sizes
- [ ] Card value colors match picker selection
- [ ] Card label colors and transforms work
- [ ] Section headings use configured size/weight/color
- [ ] Convoy status tables show correct font size
- [ ] Total stock text uses table font size
- [ ] Border radius and shadow effects visible on cards

### Configuration Scenarios
- [ ] Increase value font size to 3.0rem → numbers get larger
- [ ] Change value color to red (#ff0000) → metric values turn red
- [ ] Set heading size to 2.0rem → section headers get bigger
- [ ] Reduce table font to 0.7rem → table text shrinks
- [ ] Change heading color to blue (#0000ff) → headers turn blue

## Technical Details

### Config Structure
```json
{
  "styles": {
    "card": {
      "background": "#ffffff",
      "border_radius": 10,
      "border_color": "#667eea",
      "border_width": 4,
      "padding": "1rem",
      "shadow": "0 2px 8px rgba(0,0,0,0.1)",
      "width": 0,
      "height": 0
    },
    "value": {
      "font_size": "1.6rem",
      "font_weight": "bold",
      "color": "#667eea"
    },
    "label": {
      "font_size": "0.8rem",
      "font_weight": "bold",
      "color": "#666666",
      "text_transform": "uppercase"
    },
    "heading": {
      "font_size": "1.5rem",
      "font_weight": "bold",
      "color": "#333333"
    },
    "table": {
      "font_size": "0.9rem",
      "header_bg": "#f8f9fa"
    }
  }
}
```

### Backwards Compatibility
The renderer maintains backwards compatibility with old flat-style configs:
- Old: `style["value_size"]` → New: `style["value"]["font_size"]`
- Old: `style["label_color"]` → New: `style["label"]["color"]`
- Falls back to old keys if nested structure not found

## Troubleshooting

### Styles Not Applying
1. **Check if config saved**: Look for success message after clicking Save
2. **Refresh dashboard**: Navigate away and back to Home
3. **Check browser cache**: Hard refresh (Ctrl+F5)
4. **Verify config loaded**: Check debug panel in customization page

### Font Size Not Changing
1. **Ensure value in valid range**: 0.5rem to 5.0rem
2. **Check rem vs px**: System uses rem units (relative to base font)
3. **Browser zoom**: Reset browser zoom to 100%

### Colors Not Showing
1. **Use hex format**: Colors must be in #RRGGBB format
2. **Check color picker**: Ensure valid hex code entered
3. **Transparent colors**: Avoid colors with alpha channel

## Related Files
- `app_pages/dashboard_customization.py` - Style configuration UI
- `dashboard_widgets.py` - Style rendering logic
- `dashboard_config.py` - Config persistence

## Future Enhancements
- [ ] More granular table styling (row colors, borders)
- [ ] Custom CSS injection
- [ ] Theme presets (light/dark/high-contrast)
- [ ] Font family selection
- [ ] Animation controls
