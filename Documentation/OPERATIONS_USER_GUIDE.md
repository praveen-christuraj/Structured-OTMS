# How to Use the Fixed Operations Configuration

## Overview
The operations configuration has been fixed to properly separate different types of operational items by category. This ensures that items added to different categories (Operation, Cargo Type, Destination, Loading Berth) appear only in their intended dropdowns.

## Step-by-Step Guide

### 1. Navigate to Location Settings → Operations

1. Open the application and go to **Location Settings**
2. Select your location from the dropdown
3. Click on the **Operations** section in the radio buttons

### 2. Configuring Operations for Tanker Asset

#### Adding Operations (e.g., "Receipt from Aggu")
1. **Asset**: Select "**Tanker**"
2. **Category**: Select "**Operation**"
3. **Name**: Enter operation name (e.g., "Receipt from Aggu", "Dispatch to GPP")
4. Click **➕ Add Operation**

**Expected Result**: These items will appear ONLY in the **Operation** dropdown in Tanker Transactions

#### Adding Cargo Types (e.g., "Crude Oil")
1. **Asset**: Select "**Tanker**"
2. **Category**: Select "**Cargo Type**"
3. **Name**: Enter cargo type name (e.g., "Crude Oil", "Condensate", "OKW", "ANZ")
4. Click **➕ Add Operation**

**Expected Result**: These items will appear ONLY in the **Cargo** dropdown in Tanker Transactions

#### Adding Destinations (e.g., "Aggu")
1. **Asset**: Select "**Tanker**"
2. **Category**: Select "**Destination**"
3. **Name**: Enter destination name (e.g., "Aggu", "OFS", "GPP", "Ndoni")
4. Click **➕ Add Operation**

**Expected Result**: These items will appear ONLY in the **Destination** dropdown in Tanker Transactions

#### Adding Loading Berths (e.g., "Berth A")
1. **Asset**: Select "**Tanker**"
2. **Category**: Select "**Loading Berth**"
3. **Name**: Enter berth name (e.g., "Berth A", "Loading Bay 1", "Aggu")
4. Click **➕ Add Operation**

**Expected Result**: These items will appear ONLY in the **Loading Bay** dropdown in Tanker Transactions

### 3. Configuring Operations for Tank Asset

#### Adding Tank Operations
1. **Asset**: Select "**Tank**"
2. **Category**: Select "**Operation**"
3. **Name**: Enter operation name (e.g., "Receipt", "Dispatch", "Opening Stock")
4. Click **➕ Add Operation**

**Expected Result**: These items will appear ONLY in the **Operation** dropdown in Tank Transactions

### 4. Managing Existing Operations

#### View All Operations
- Check the **"Show only selected Asset/Category"** checkbox to filter the list
- Uncheck it to see all operations across all assets and categories

#### Enable/Disable Operations
- Use the **Active** toggle to enable/disable operations without deleting them
- Disabled operations won't appear in dropdowns

#### Delete Operations
- Click the **🗑️ Delete** button to permanently remove an operation

## Example Configuration

### Tanker Asset - Complete Setup:

**Operation (Category)**
- Receipt from Aggu
- Receipt from OFS
- Dispatch to GPP
- Dispatch to Ndoni
- Opening Stock

**Cargo Type (Category)**
- Crude Oil
- Condensate
- OKW
- ANZ

**Destination (Category)**
- Aggu
- OFS
- Ogini
- GPP
- Ndoni
- Bonny

**Loading Berth (Category)**
- Berth A
- Berth B
- Loading Bay 1
- Aggu
- Ogini

### What This Looks Like in Tanker Transactions:

| Field | Shows Items From | Example Values |
|-------|------------------|-----------------|
| **Cargo** | Cargo Type category | Crude Oil, Condensate, OKW, ANZ |
| **Operation** | Operation category | Receipt from Aggu, Dispatch to GPP |
| **Destination** | Destination category | Aggu, OFS, Ogini, GPP, Ndoni, Bonny |
| **Loading Bay** | Loading Berth category | Berth A, Berth B, Loading Bay 1 |

## Key Points to Remember

✅ **Separation by Category**: Each category populates a specific dropdown
- **Operation** → Operation dropdown
- **Cargo Type** → Cargo dropdown
- **Destination** → Destination dropdown
- **Loading Berth** → Loading Bay dropdown

✅ **Separation by Asset**: Operations are also organized by asset
- Tank operations are separate from Tanker operations
- Each asset has its own Operation, Cargo Type, Destination, etc.

✅ **Active/Inactive Flag**: 
- Only ACTIVE items appear in dropdowns
- Use the toggle to disable items temporarily without deleting them

✅ **No Merging**: 
- Items added to different categories will NO LONGER merge
- Each dropdown will only show items from its designated category

## Troubleshooting

### Problem: My Cargo items aren't showing up
**Solution**: 
1. Go to Location Settings → Operations
2. Verify you added items with Asset="**Tanker**" and Category="**Cargo Type**"
3. Check that they are marked as **Active** (toggle ON)

### Problem: Operations are mixed with other items
**Solution**: This should no longer happen with the fix. Make sure you're:
1. Selecting the correct Category when adding items
2. Verifying in Tanker Transactions that each dropdown shows only its category items

### Problem: Tank operations appearing in Tanker Transactions
**Solution**: Make sure you added operations with:
- Asset = "**Tanker**" (not "Tank")
- Category = "**Operation**"

## Contact Support
If you encounter any issues with the operations configuration, please verify:
1. The asset is correctly selected (Tank vs Tanker)
2. The category matches the intended dropdown
3. The items are marked as Active
4. You've saved the changes
