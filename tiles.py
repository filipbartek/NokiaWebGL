import logging

from sys import argv
from struct import unpack, pack
from math import log, pow, pi, ceil
from urlparse import urljoin
from urllib import urlopen

from ModestMaps.Geo import Location, MercatorProjection, deriveTransformation

from TileStache.Core import KnownUnknown

def fromNokia(x, y, zoom):
    """ Return column, row, zoom for Nokia x, y, z.
    """
    row = int(pow(2, zoom) - y - 1)
    col = x
    return col, row, zoom

def toNokia(col, row, zoom):
    """ Return x, y, z for Nokia tile column, row, zoom.
    """
    x = col
    y = int(pow(2, zoom) - row - 1)
    return x, y, zoom

def coordinatePath(coord):
    """
    """
    x, y, z = toNokia(int(coord.column), int(coord.row), int(coord.zoom))
    
    #
    # maximum number of digits in row or column at this zoom
    # and a zero-padded string format for integers.
    #
    len = ceil(log(2 ** z) / log(10))
    fmt = '%%0%dd' % len
    
    row, col = fmt % y, fmt % x
    
    if len == 4:
        dir = '%s%s/%s%s' % (row[0:2], col[0:2], row[2:3], col[2:3])
    elif len == 5:
        dir = '%s%s/%s%s' % (row[0:2], col[0:2], row[2:4], col[2:4])
    elif len == 6:
        dir = '%s%s/%s%s/%s%s' % (row[0:2], col[0:2], row[2:4], col[2:4], row[4:5], col[4:5])
    else:
        raise BadZoom('len = %d unsupported' % len)
    
    return '%(z)d/%(dir)s/map_%(z)d_%(y)d_%(x)d' % locals()

def coordinateHeights(tile_coord):
    """
    """
    lut_coord = tile_coord.zoomTo(13).container() # height lookup tables exist only at z13
    server = 'bcde'[int(lut_coord.row + lut_coord.column + lut_coord.zoom) % 4]
    path = coordinatePath(lut_coord)

    url = 'http://%(server)s.maps3d.svc.nokia.com/data4/%(path)s.lut' % locals()
    
    data = urlopen(url).read()
    zoom = tile_coord.zoom - lut_coord.zoom
    
    #
    # Skip to the beginning of the correct zoom level in the mipmap
    #
    
    dim = 2**zoom, 2**zoom
    off = sum([0] + [4**i for i in range(zoom)])
    
    #
    # Skip to the correct row in the mipmap zoom level, but use the "col"
    # value because the data is actually stored on its side, west-up.
    #
    
    col = tile_coord.column - lut_coord.zoomTo(tile_coord.zoom).column
    off += int(col) * 2**zoom
    
    #
    # Skip to the correct column in the mipmap zoom level, but use the "row"
    # value because the data is actually stored on its side, west-up.
    #
    
    row = tile_coord.row - lut_coord.zoomTo(tile_coord.zoom).row
    off += 2**zoom - int(row + 1)
    
    logging.debug('row, col, off: %.3f, %.3f, %d, %d, %s' % (row, col, off*4, 5461*4 + off, repr(data[5461*4 + off])))
    
    #
    # Read bottom and top heights in meters.
    #
    
    bottom, top = unpack('<HH', data[off*4:off*4+4])
    
    return bottom, top

def extract_vertices(data, count, bottom, top):
    """
    """
    zxy_data, uv_data = data[:count*12], data[count*12:]
    
    zxy_values = [unpack('<fff', zxy_data[off:off+12]) for off in range(0, count*12, 12)]
    uv_values = [unpack('<ff', uv_data[off:off+8]) for off in range(0, count*8, 8)]
    
    scale = (top - bottom) / 2**16
    vertices = [(x/256, y/256, (bottom + scale*z)/256, u, v) for ((z, x, y), (u, v)) in zip(zxy_values, uv_values)]
    
    return vertices

def extract_faces(data, count):
    """
    """
    triangles = [unpack('<HHH', data[off:off+6]) for off in range(0, count*6, 6)]
    
    return triangles

def get_projection():
    ''' Return the correct spherical mercator project for Nokia.
    '''
    # the spherical mercator world tile covers (-π, -π) to (π, π)
    t = deriveTransformation(-pi, pi, 0, 0, pi, pi, 1, 0, -pi, -pi, 0, 1)
    return MercatorProjection(0, t)

def get_tile_data(coord):
    """
    """
    server = 'bcde'[int(coord.row + coord.column + coord.zoom) % 4]
    path = coordinatePath(coord)
    
    url = 'http://%(server)s.maps3d.svc.nokia.com/data4/%(path)s.n3m' % locals()

    #
    # Attempt to load the data.
    #

    data = urlopen(url).read()

    if not data:
        return ()
    
    #
    # Lookup the bottom and top of the tile data in meters, and convert
    # that to a scale value for the raw z-axis based on current latitude.
    #
    proj = get_projection()
    
    lat_span = abs(proj.coordinateLocation(coord).lat - proj.coordinateLocation(coord.down()).lat)
    meter_span = 6378137 * pi * lat_span / 180.0
    
    bottom, top = coordinateHeights(coord)
    logging.debug('bottom, top (m): %d, %d' % (bottom, top))
    
    bottom, top = bottom * 2**16 / meter_span, top * 2**16 / meter_span
    logging.debug('bottom, top (u): %d, %d' % (bottom, top))
    
    #
    # Count the textures in the data.
    #
    
    (textures, ) = unpack('<i', data[4:8])
    
    logging.debug('textures: %d' % textures)
    
    #
    # Pick out the vertices for the geometry,
    # as lists of (x, y, z, u, v) coordinates.
    #
    
    off = 12
    vertex_blocks = [unpack('<ii', data[off:off+8]) for off in range(off, off + textures * 8, 8)]
    vertex_data = [extract_vertices(data[start:], count, bottom, top) for (start, count) in vertex_blocks]
    
    logging.debug('vertex blocks: %s' % repr(vertex_blocks))

    for i in range(textures):
        tex_info = [i, len(vertex_data[i])]
        tex_info += map(min, zip(*vertex_data[i]))
        tex_info += map(max, zip(*vertex_data[i]))
        logging.debug('vertices %d - %d (%.3f, %.3f, %.3f, %.3f, %.3f) to (%.3f, %.3f, %.3f, %.3f, %.3f)' % tuple(tex_info))
    
    #
    # Pick out the faces for each texture as triples of vertex indexes.
    #
    
    off = 12 + textures * 8
    face_blocks = [unpack('<ii', data[off:off+8]) for off in range(off, off + textures * 16, 16)]
    face_data = [extract_faces(data[start:], count) for (start, count) in face_blocks]
    
    logging.debug('face blocks: %s' % repr(face_blocks))

    for i in range(textures):
        face_info = [i, len(face_data[i])]
        face_info += map(min, zip(*face_data[i]))
        face_info += map(max, zip(*face_data[i]))
        logging.debug('faces %d - %d (%d, %d, %d) to (%d, %d, %d)' % tuple(face_info))
    
    #
    # Pick out the filenames of the JPEG textures,
    # stored as ASCII strings deeper in the file.
    #
    
    off = 12 + textures * 8
    bitmap_blocks = [unpack('<ii', data[off+8:off+16]) for off in range(off, off + textures * 16, 16)]
    imagename_blocks = [(start + 1, unpack('<B', data[start:start+1])[0]) for (index, start) in bitmap_blocks]
    image_names = [data[start:start+length] for (start, length) in imagename_blocks]
    image_urls = [urljoin(url, name) for name in image_names]
    
    logging.debug('bitmap blocks: %s' % repr(bitmap_blocks))
    logging.debug('image urls: %s' % ', '.join(image_urls))
    
    #
    # Return a list of tuples, each with three items:
    # 1. list of vertices, (x, y, z, u, v)
    # 2. list of faces, 3-tuple of vertex indexes
    # 3. texture image URL
    #
    
    return zip(vertex_data, face_data, image_urls)

class BadZoom (Exception): pass

class PackableFloatList (list):
    ''' Wrapper for a list of floats with a TileStache-compatible save method.
    
        Used by TileProvider, see also http://tilestache.org/doc/#custom-providers
    '''
    def save(self, output, format):
        format = '<fff' if (format == 'Little Endian') else '>fff'
        
        for (x, y, z) in zip(self[0::3], self[1::3], self[2::3]):
            output.write(pack(format, x, y, z))

class TileProvider:
    ''' TileStache tile provider.
    
        See also http://tilestache.org/doc/#custom-providers
    '''
    def __init__(self, layer):
        self.layer = layer
        
    def getTypeByExtension(self, extension):
        '''
        '''
        if extension == 'big':
            return 'application/octet-stream', 'Big Endian'

        if extension == 'little':
            return 'application/octet-stream', 'Little Endian'
        
        raise KnownUnknown('Unknown type: "%s".' % extension)
    
    def renderTile(self, width, height, srs, coord):
        '''
        
            Arguments for width, height and srs are ignored.
        '''
        data = PackableFloatList()
        
        for (vertices, faces, image_urls) in get_tile_data(coord):
            for (v0, v1, v2) in faces:
                for (x, y, z, u, v) in (vertices[v0], vertices[v1], vertices[v2]):
                    # overlap by one tile-pixel
                    x = (x - 1) * 258./65536.
                    y = (y - 1) * 258./65536.
                    z = (z - 1) * 258./65536.
                
                    data.extend([x, y, z])
        
        return data

if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG, format='%(filename)s %(lineno)d - %(msg)s')

    
    def GetData(latx,lonx,zoomx):
        p = get_projection()

        lat = latx
        lon = lonx
        zoom = zoomx
    
        loc = Location(lat, lon)
        coord = p.locationCoordinate(loc).zoomTo(zoom)
    
        return coord
   
    
    #
    # Output .obj files and JPEGs locally.
    #
    def OutputTile(coord,textures,objnum,offsetx,offsety):
        for (index, (vertices, faces, image_url)) in enumerate(textures):
            
            #coordstr = (str(coord.row) +"_"+ str(coord.column)+"_"+str(coord.zoom))
            coordstr = str(objnum)+"_OBJECT"#simpler filename
            
            obj = open('out_%s_%d.obj' % (coordstr,index), 'w')

            mtl = open('out_%s_%d.mtl' % (coordstr,index), 'w')
            #material file
            print >> mtl, 'newmtl out_%s_%d_mat' % (coordstr,index) #material name
            print >> mtl, 'map_Ka out_%s_%d.jpg' % (coordstr,index) #ambient texture
            print >> mtl, 'map_Kd out_%s_%d.jpg' % (coordstr,index) #diffuse texture
            # material lib name
            print >> obj, 'mtllib out_%s_%d.mtl' % (coordstr,index)
            # object name
            print >> obj, 'g out_%s_%d' % (coordstr,index)
            # material to use
            print >> obj, 'usemtl out_%s_%d_mat' % (coordstr,index)
            # object file
            for (x, y, z, u, v) in vertices:
                print >> obj, 'v %.1f %.1f %.1f' % (x+offsetx, y+offsety, z)
            
            for (x, y, z, u, v) in vertices:
                print >> obj, 'vt %.6f %.6f' % (u, v)
            
            for (v0, v1, v2) in faces:
                print >> obj, 'f %d/%d %d/%d %d/%d' % (v0+1, v0+1, v1+1, v1+1, v2+1, v2+1)
        
            jpg = open('out_%s_%d.jpg' % (coordstr,index), 'wb')
            jpg.write(urlopen(image_url).read())

def saveTiles(tiles, filename='out'):
    """
    Save tiles into an OBJ file accompanied with a MTL file and one
    or more texture files.
    """
    import os
    import urlparse

    mtl_filename = '%s.mtl' % (filename)
    obj_filename = '%s.obj' % (filename)

    obj = open(obj_filename, 'w')
    mtl = open(mtl_filename, 'w')

    # TODO: Print file header with human readable specification of ROI.
    print >> obj, 'mtllib %s' % (mtl_filename)

    # Vertex index offset
    v_offset = 1

    for (textures, column, row, offset_x, offset_y) in tiles:
        tile_name = (column, row)

        # Object name (tile)
        # TODO: Print proper tile name.
        #print >> obj, 'o %s' % (tile_name)

        for (index, (vertices, faces, image_url)) in enumerate(textures):
            image_path = urlparse.urlparse(image_url).path
            image_filename = os.path.split(image_path)[1]
            mtl_name = os.path.splitext(image_filename)[0]

            # Add material in MTL file
            print >> mtl, 'newmtl %s' % (mtl_name) #material name
            print >> mtl, 'map_Ka %s' % (image_filename) #ambient texture
            print >> mtl, 'map_Kd %s' % (image_filename) #diffuse texture

            # OBJ file:

            # Group name (tile component)
            print >> obj, 'g %s' % (mtl_name)

            # Material for this group
            print >> obj, 'usemtl %s' % (mtl_name)

            # Vertices
            for (x, y, z, u, v) in vertices:
                # TODO: Set offsetx and offsety
                print >> obj, 'v %.1f %.1f %.1f' % (x + offset_x, y + offset_y, z)

            # Texture coordinates
            for (x, y, z, u, v) in vertices:
                print >> obj, 'vt %.6f %.6f' % (u, v)

            # Faces
            for (v0, v1, v2) in faces:
                v0_file = v0 + v_offset
                v1_file = v1 + v_offset
                v2_file = v2 + v_offset
                print >> obj, 'f %d/%d %d/%d %d/%d' % (v0_file, v0_file, v1_file, v1_file, v2_file, v2_file)

            jpg = open('%s' % (image_filename), 'wb')
            jpg.write(urlopen(image_url).read())

            # Increase vertex index offset
            v_offset += len(vertices)

def intCoord(lat, lon, zoom=19):
    import types
    import ModestMaps
    assert type(zoom) is types.IntType
    floatCoord = GetData(lat, lon, zoom)
    result = ModestMaps.Core.Coordinate(int(floatCoord.row), int(floatCoord.column), floatCoord.zoom)
    assert type(result.zoom) is types.IntType
    return result

# These values are used to offset the tiles in the result composed OBJ file
tile_size_x = 256.0
tile_size_y = 256.0

def saveRoi(latBegin, latEnd, lonBegin, lonEnd, zoom=19):
    """
    Save the region of interest specified by the parameters to an OBJ file
    accompanied with a MTL file and one or more texture files.
    """

    import ModestMaps

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
            tiles.append((textures, column, row, offset_x, offset_y))

    # Save the structure in and OBJ file
    saveTiles(tiles)

if __name__ == '__main__':
    prague_lat = 50.0893
    prague_lon = 14.3994

    latBegin = prague_lat
    latEnd = prague_lat
    lonBegin = prague_lon
    lonEnd = prague_lon
    zoom = 19

    # TODO: Let the user specify output directory and filename(s).
    if len(argv) == 1:
        logging.debug('Fetching default ROI')
    elif len(argv) == 3:
        logging.debug('Fetching one tile ROI at default zoom level')
        latBegin = float(argv[1])
        latEnd = latBegin
        lonBegin = float(argv[2])
        lonEnd = lonBegin
    elif len(argv) == 4:
        logging.debug('Fetching one tile ROI at custom zoom level')
        latBegin = float(argv[1])
        latEnd = latBegin
        lonBegin = float(argv[2])
        lonEnd = lonBegin
        zoom = int(argv[3])
    elif len(argv) == 5:
        logging.debug('Fetching range ROI at default zoom level')
        latBegin = float(argv[1])
        latEnd = float(argv[2])
        lonBegin = float(argv[3])
        lonEnd = float(argv[4])
    elif len(argv) == 6:
        logging.debug('Fetching range ROI at custom zoom level')
        latBegin = float(argv[1])
        latEnd = float(argv[2])
        lonBegin = float(argv[3])
        lonEnd = float(argv[4])
        zoom = int(argv[5])
    else:
        raise Exception('Incorrect number of arguments')

    saveRoi(latBegin, latEnd, lonBegin, lonEnd, zoom)
