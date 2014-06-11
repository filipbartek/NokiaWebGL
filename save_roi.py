from tiles import GetData, logging, get_tile_data

# These values are used to offset the tiles in the result composed OBJ file
tile_size_x = 256.0
tile_size_y = 256.0

def intCoord(lat, lon, zoom=19):
    import ModestMaps
    floatCoord = GetData(lat, lon, zoom)
    result = ModestMaps.Core.Coordinate(int(floatCoord.row), int(floatCoord.column), int(floatCoord.zoom))
    return result

def save_roi(latBegin, latEnd, lonBegin, lonEnd, zoom=19):
    """
    Save the region of interest specified by the parameters to an OBJ file
    accompanied with a MTL file and one or more texture files.
    """

    import ModestMaps
    from TileCombiner import TileCombiner

    assert latEnd >= latBegin
    assert lonEnd >= lonBegin

    coordBegin = intCoord(latBegin, lonBegin, zoom)
    coordEnd = intCoord(latEnd, lonEnd, zoom)

    columnBegin = coordBegin.column
    columnEnd = coordEnd.column
    assert columnEnd >= columnBegin
    # Transformation swaps row polarity
    rowEnd = coordBegin.row
    rowBegin = coordEnd.row
    assert rowEnd >= rowBegin

    columnNum = columnEnd - columnBegin + 1
    rowNum = rowEnd - rowBegin + 1

    logging.debug('Tiles in ROI: %d x %d' % (columnNum, rowNum))

    tc = TileCombiner('out', 'out')

    # Get vertices, faces and textures for each tile
    tiles = []
    for columnId in range(columnNum):
        column = columnBegin + columnId
        for rowId in range(rowNum):
            row = rowBegin + rowId
            coord = ModestMaps.Core.Coordinate(row, column, zoom)
            textures = get_tile_data(coord)
            offset_x = columnId * tile_size_x
            offset_y = (rowNum - rowId - 1) * tile_size_y
            tc.addTile(textures, offset_x, offset_y)
