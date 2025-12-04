var alerts = ee.Image("projects/ee-dfgm2006/assets/fires_colombia/Change_Alerts_S2")
var forrest = ee.Image("projects/ee-dfgm2006/assets/cambio2017-2018")

var fnf = forrest.select("b1").eq(1).selfMask()

Map.addLayer(fnf.randomVisualizer())

// var gte = ee.Image(alerts.mask(fnf))
var gte = ee.Image(alerts)

var aoi = geometry

print(gte)
Map.addLayer(gte)

function decimalYearToEeDate(decimalYear) {
  var dec = ee.Number(decimalYear);
  var year = dec.floor();
  var fraction = dec.subtract(year);

  var startOfYear = ee.Date.fromYMD(year, 1, 1);
  var nextYear = startOfYear.advance(1, 'year');

  var daysInYear = nextYear.difference(startOfYear, 'day');
  var daysOffset = fraction.multiply(daysInYear);

  return startOfYear.advance(daysOffset, 'day');
}

// ee.Date -> decimal year (scalar)
function dateToDecimalYear(date) {
  date = ee.Date(date);
  var year = ee.Number.parse(date.format('Y'));
  var startOfYear = ee.Date.fromYMD(year, 1, 1);
  var nextYear = startOfYear.advance(1, 'year');
  var daysInYear = nextYear.difference(startOfYear, 'day');
  var daysSinceStart = date.difference(startOfYear, 'day');
  return year.add(daysSinceStart.divide(daysInYear));
}


// ============================
// 2. USE confirmation_date + TIME WINDOW
// ============================

var confDate = gte.select('confirmation_date');
var confMask = confDate.gt(0);

// approximate time range in AOI using a coarse reduceRegion
var confStats = confDate.updateMask(confMask).reduceRegion({
  reducer: ee.Reducer.minMax(),
  geometry: aoi,
  scale: 500,       // coarse for speed
  maxPixels: 1e7
});

print('confirmation_date stats (decimal years)', confStats);

var minDec = ee.Number(confStats.get('confirmation_date_min'));
var maxDec = ee.Number(confStats.get('confirmation_date_max'));

// if empty, these will be null; just a quick guard:
print('minDec', minDec, 'maxDec', maxDec);

var startDate = decimalYearToEeDate(minDec).advance(-7, 'day');
var endDate   = decimalYearToEeDate(maxDec).advance(7, 'day');

print('FIRMS time window', startDate, endDate);


// ============================
// 3. PUT confirmation_date ONTO 1 KM GRID
// ============================

var scaleFirms = 1000;  // MODIS-ish

var confDate1km = confDate
  .clip(aoi);

var confMask1km = confMask
  .clip(aoi);

Map.addLayer(confMask1km, {min:0, max:1, palette:['yellow']},
             'confirmation>0 mask (1km)');


// ============================
// 4. BUILD FIRE-ALERT MASK FROM MODIS FIRMS
// ============================

var deltaDays = 3;                         // ±3 days
var deltaYear = ee.Number(deltaDays).divide(365);  // in decimal years

// MODIS FIRMS collection
var modisIC = ee.ImageCollection('FIRMS')
  .filterBounds(aoi)
  .filterDate(startDate, endDate);
  
var imgx = ee.Image(modisIC.toList(modisIC.size()).get(1))
Map.addLayer(imgx)


// For each MODIS FIRMS image: make a fire-alert mask at 1 km
var fireAlertIC = modisIC.map(function(img) {
  // 1) Fire pixels: T21 > 0
  var fire = img.select('T21')
    .gt(0)
    .selfMask()
    .clip(aoi);

  // 2) Temporal match with confirmation_date1km
  var imgDate = ee.Date(img.get('system:time_start'));
  var imgDecYear = dateToDecimalYear(imgDate);   // scalar

  var dyImg = ee.Image.constant(imgDecYear)
    .toFloat()
    .clip(aoi);

  var temporalMatch = confDate1km
    .subtract(dyImg)
    .abs()
    .lte(deltaYear)
    .updateMask(confMask1km);

  // 3) Spatio-temporal match = fire AND temporalMatch
  var fireAlert = fire.and(temporalMatch);

  return fireAlert.rename('fire_alert')
    .copyProperties(img, ['system:time_start']);
});

print('Number of MODIS FIRMS images used', fireAlertIC.size());

var imgx = ee.Image(fireAlertIC.toList(fireAlertIC.size()).get(0))
Map.addLayer(imgx)

// Collapse over time (OR)
var fireAlert1km = fireAlertIC
  .max()
  .rename('fire_alert_1km')
  .clip(aoi);
  
print('>>>>>>>sum fireAlert1km', fireAlert1km.reduceRegion({
  reducer: ee.Reducer.sum(),
  geometry: aoi,
  scale: 1000,
  maxPixels: 1e7
}));


Map.addLayer(fireAlert1km,
  {min:0, max:1, palette:['black','red']},
  'Fire-alert mask 1km (MODIS, conf_date)');


// Final: gte filtered by FIRMS
var gte_filtered_by_firms = gte.updateMask(fireAlert1km);

print('gte_filtered_by_firms', gte_filtered_by_firms);

// Quick visualization of difference band
Map.addLayer(
  gte.select('difference').updateMask(confMask).clip(aoi),
  {min:-0.6, max:0, palette:['blue','yellow']},
  'All alerts (gte, difference)'
);

Map.addLayer(
  gte_filtered_by_firms.select('difference').clip(aoi),
  {min:-0.6, max:0, palette:['red','yellow']},
  'FIRMS-confirmed fire alerts (difference)'
);


print('>>>>>>sum gte_filtered_by_firms difference', 
  gte_filtered_by_firms.select('difference').reduceRegion({
    reducer: ee.Reducer.count(),
    geometry: aoi,
    scale: 30,   // your native res
    maxPixels: 1e7
}));

