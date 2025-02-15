from matplotlib.patches import RegularPolygon,Rectangle
from matplotlib.colors import to_rgba
from yambopy.lattice import bravais_types
import numpy as np

def add_fig_kwargs(func):
    """
    Decorator that adds keyword arguments for functions returning matplotlib
    figures.

    Taken from pymatgen:
    http://pymatgen.org/
    https://github.com/materialsproject/pymatgen
    """
    def wrapper(*args, **kwargs):
        # pop the kwds used by the decorator.
        title = kwargs.pop("title", None)
        show = kwargs.pop("show", True)
        savefig = kwargs.pop("savefig", None)

        # Call func and return immediately if None is returned.
        fig = func(*args, **kwargs)
        if fig is None:
            return fig

        # Operate on matplotlib figure.
        if title is not None:
            fig.suptitle(title)
        if savefig:
            fig.savefig(savefig)
        if show:
            import matplotlib.pyplot as plt
            plt.show()
        return fig
    return wrapper

def BZ_Wigner_Seitz(lattice,center=(0.,0.),orientation=np.radians(30),color='white',linewidth=2):
    """
    Wrapper function to decide which BZ shape to show
    """
    lat_type = bravais_types(lattice.lat,lattice.alat[0])[:3]
    if lat_type=='Hex': return BZ_hexagon(lattice.rlat,center=center,orientation=orientation,color=color,linewidth=linewidth)
    if lat_type=='Ort': return BZ_rectangle(lattice.rlat,color=color,linewidth=linewidth)

def BZ_hexagon(rlat,center=(0.,0.),orientation=np.radians(30),color='white',linewidth=2):
    """
    Returns hexagonal borders of 2D Wigner-Seitz cells to aid in k/q-space plotting
    to be added with ax.add_patch(BZ_hexagon)

    - rlat: reciprocal lattice vectors from YamboLatticeDB
    - center,orientation, color, linewidth are RegularPolygon parameters
    """

    # Reshape rlat
    rlat = np.array([[rlat[0,0],rlat[0,1]],[rlat[1,0],rlat[1,1]]])

    # Hexagon radius
    radius = np.linalg.norm(rlat[0]/np.sqrt(3.))

    # Matplotlib patch
    hexagon=RegularPolygon(center,numVertices=6,radius=radius,\
                           orientation=orientation,facecolor=to_rgba('white',0.),\
                           edgecolor=to_rgba(color,1.),linewidth=linewidth)

    return hexagon

def BZ_rectangle(rlat,color='white',linewidth=2):
    """
    Returns square borders of 2D Wigner-Seitz cells to aid in k/q-space plotting
    to be added with ax.add_patch(BZ_rectangle)

    - rlat: reciprocal lattice vectors from YamboLatticeDB
    - color, linewidth are RegularPolygon parameters
    """

    # Reshape rlat
    rlat = np.array([[rlat[0,0],rlat[0,1]],[rlat[1,0],rlat[1,1]]])

    # Matplotlib patch
    width, height  = rlat[0,0], rlat[1,1]
    origin = [-width/2.,-height/2.]
    rectangle = Rectangle(origin,width,height,facecolor=to_rgba('white',0.),\
                          edgecolor=to_rgba(color,1.),linewidth=linewidth)

    return rectangle

def shifted_grids_2D(k,b):
    """
    Shift a 2D k/q-point in the adjacent BZs.

    Inputs: 
    - k is kgrid in c.c.
    - b is ylat.rlat in c.c. (reciprocal lattice vectors) 

    Returns a list of the original plus the eight 2D shifted grids
    """
    N_k = len(k)
    N_dim = 2
    N_BZ  = 9
    
    c = []
    for i in range(-N_dim+1,N_dim): # Fill translation coefficients
        for j in range(-N_dim+1,N_dim): c.append( [i,j] )

    shifted_grids = []
    for ig in range(N_BZ): # Each shifted grid is an element of the list
        k_shift = np.zeros((N_k,3))
        for i in range(N_dim): 
            k_shift[:,i] = k[:,i]+c[ig][0]*b[0,i]+c[ig][1]*b[1,i]   
        shifted_grids.append(k_shift)

    return shifted_grids


