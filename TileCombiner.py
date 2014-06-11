import os
import urlparse
import urllib

class TileCombiner():
    """
    Saves tiles into an OBJ file accompanied with a MTL file and one
    or more texture files.
    """

    def __init__(self, filename='out', dir=''):
        self.path = dir

        if not os.path.exists(self.path):
            os.makedirs(self.path)

        obj_filename = '%s.obj' % (filename)
        mtl_filename = '%s.mtl' % (filename)

        self.obj = open(os.path.join(self.path, obj_filename), 'w')
        self.mtl = open(os.path.join(self.path, mtl_filename), 'w')

        # TODO: Print file header with human readable specification of ROI.
        print >> self.obj, 'mtllib %s' % (mtl_filename)

        self.v_offset = 1
        self.tile_id = 0

    def __del__(self):
        self.obj.close()
        self.mtl.close()

    def addTile(self, textures, offset_x=0, offset_y=0, tile_name=None):
        if tile_name is None:
            tile_name = str(self.tile_id)
        print >> self.obj, 'o %s' % (tile_name)

        for (index, (vertices, faces, image_url)) in enumerate(textures):
            image_path = urlparse.urlparse(image_url).path
            image_filename = os.path.split(image_path)[1]
            mtl_name = os.path.splitext(image_filename)[0]

            # Add material in MTL file
            print >> self.mtl, 'newmtl %s' % (mtl_name) #material name
            print >> self.mtl, 'map_Ka %s' % (image_filename) #ambient texture
            print >> self.mtl, 'map_Kd %s' % (image_filename) #diffuse texture

            # OBJ file:

            # Group name (tile component)
            print >> self.obj, 'g %s' % (mtl_name)

            # Material for this group
            print >> self.obj, 'usemtl %s' % (mtl_name)

            # Vertices
            for (x, y, z, u, v) in vertices:
                print >> self.obj, 'v %.1f %.1f %.1f' % (x + offset_x, y + offset_y, z)

            # Texture coordinates
            for (x, y, z, u, v) in vertices:
                print >> self.obj, 'vt %.6f %.6f' % (u, v)

            # Faces
            for (v0, v1, v2) in faces:
                v0_file = v0 + self.v_offset
                v1_file = v1 + self.v_offset
                v2_file = v2 + self.v_offset
                print >> self.obj, 'f %d/%d %d/%d %d/%d' % (v0_file, v0_file, v1_file, v1_file, v2_file, v2_file)

            with open(os.path.join(self.path, image_filename), 'wb') as jpg:
                jpg.write(urllib.urlopen(image_url).read())

            # Increase vertex index offset
            self.v_offset += len(vertices)

        self.tile_id += 1
