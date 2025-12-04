import ee


def decimal_year_to_ee_date(decimal_year):
    """
    Convert decimal year to ee.Date.
    Example: 2024.5 -> July 2, 2024 (middle of the year)
    
    Args:
        decimal_year: ee.Number representing year as decimal
        
    Returns:
        ee.Date
    """
    dec = ee.Number(decimal_year)
    year = dec.floor()
    fraction = dec.subtract(year)
    
    start_of_year = ee.Date.fromYMD(year, 1, 1)
    next_year = start_of_year.advance(1, 'year')
    
    days_in_year = next_year.difference(start_of_year, 'day')
    days_offset = fraction.multiply(days_in_year)
    
    return start_of_year.advance(days_offset, 'day')


def date_to_decimal_year(date):
    """
    Convert ee.Date to decimal year.
    Example: July 2, 2024 -> 2024.5 (approximately)
    
    Args:
        date: ee.Date
        
    Returns:
        ee.Number representing decimal year
    """
    date = ee.Date(date)
    year = ee.Number.parse(date.format('Y'))
    start_of_year = ee.Date.fromYMD(year, 1, 1)
    next_year = start_of_year.advance(1, 'year')
    days_in_year = next_year.difference(start_of_year, 'day')
    days_since_start = date.difference(start_of_year, 'day')
    return year.add(days_since_start.divide(days_in_year))
