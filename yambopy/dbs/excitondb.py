
from yambopy.units import *
from yambopy.plot.plotting import add_fig_kwargs,BZ_Wigner_Seitz
from yambopy.plot.bandstructure import *
from yambopy.lattice import replicate_red_kmesh, calculate_distances, get_path
from yambopy.tools.funcs import gaussian, lorentzian
from yambopy.dbs.savedb import *
from yambopy.dbs.latticedb import *
from yambopy.dbs.electronsdb import *


class ExcitonList():
    """
    Container class to perform operations on lists of excitons
    """
    def __init__(self,excitonlist):
        self.excitonlist = excitonlist

    def __str__(self):
        lines = []; app = lines.append
        for exciton in self.excitonlist:
            app( str(exciton.get_string(singleline=True)) )
        return "\n".join(lines)

class Exciton():
    """
    Basic container of data for a single exciton
    TODO: classify the excitons according to their symmetry
    """
    def __init__(self,energy,intensity,degeneracy,coeffs=None,wf=None):
        self.energy = energy
        self.intensity = intensity
        self.degeneracy = degeneracy
        self.coeffs = coeffs
        self.wf = wf

    def get_string(self,singleline=False):
        lines = []; app = lines.append
        app( 'energy:     %8.4'%self.energy )
        app( 'intensity:  %8.4'%self.intensity )
        app( 'degeneracy: %8d'%self.degeneracy )
        if singleline: return "".join(lines)
        return "\n".join(lines)
    
    def __str__(self):
        return self.get_string()

class YamboExcitonDB(YamboSaveDB):
    """ Read the excitonic states database from yambo

        Exciton eigenvectors are arranged as eigenvectors[i_exc, i_kvc]
        Transitions are unpacked in table[ i_k, i_v, i_c, i_s_c, i_s_v ] (last two are spin indices)
    """
    def __init__(self,lattice,Qpt,eigenvalues,l_residual,r_residual,spin_pol='no',car_qpoint=None,q_cutoff=None,table=None,eigenvectors=None):
        if not isinstance(lattice,YamboLatticeDB):
            raise ValueError('Invalid type for lattice argument. It must be YamboLatticeDB')

        self.Qpt = Qpt
        self.lattice = lattice
        self.eigenvalues = eigenvalues
        self.l_residual = l_residual
        self.r_residual = r_residual
        #optional
        self.car_qpoint = car_qpoint
        self.q_cutoff = q_cutoff
        self.table = table
        self.eigenvectors = eigenvectors
        self.spin_pol = spin_pol

    @classmethod
    def from_db_file(cls,lattice,filename='ndb.BS_diago_Q1',folder='.'):
        """ initialize this class from a file
        """
        path_filename = os.path.join(folder,filename)
        if not os.path.isfile(path_filename):
            raise FileNotFoundError("File %s not found in YamboExcitonDB"%path_filename)

        # Qpoint
        Qpt = filename.split("Q",1)[1]

        with Dataset(path_filename) as database:
            if 'BS_left_Residuals' in list(database.variables.keys()):
                #residuals
                rel,iml = database.variables['BS_left_Residuals'][:].T
                rer,imr = database.variables['BS_right_Residuals'][:].T
                l_residual = rel+iml*I
                r_residual = rer+imr*I
            if 'BS_Residuals' in list(database.variables.keys()):
                #residuals
                rel,iml,rer,imr = database.variables['BS_Residuals'][:].T
                l_residual = rel+iml*I
                r_residual = rer+imr*I

            car_qpoint = None
            if 'Q-point' in list(database.variables.keys()):
                # Finite momentum
                car_qpoint = database.variables['Q-point'][:]/lattice.alat
            if Qpt=="1": car_qpoint = np.zeros(3)

            #energies
            eig =  database.variables['BS_Energies'][:]*ha2ev
            eigenvalues = eig[:,0]+eig[:,1]*I
                
            #eigenvectors
            table = None
            eigenvectors = None
            if 'BS_EIGENSTATES' in database.variables:
                eiv = database.variables['BS_EIGENSTATES'][:]
                eiv = eiv[:,:,0] + eiv[:,:,1]*I
                eigenvectors = eiv
                table = database.variables['BS_TABLE'][:].T.astype(int)

            table = table
            eigenvectors = eigenvectors
            spin_vars = [int(database.variables['SPIN_VARS'][:][0]), int(database.variables['SPIN_VARS'][:][1])]
            if spin_vars[0] == 2 and spin_vars[1] == 1:
               spin_pol = 'pol'
            else:
               spin_pol = 'no'
        # Check if Coulomb cutoff is present
        path_cutoff = os.path.join(path_filename.split('ndb',1)[0],'ndb.cutoff')  
        q_cutoff = None
        if os.path.isfile(path_cutoff):
            with Dataset(path_cutoff) as database:
                bare_qpg = database.variables['CUT_BARE_QPG'][:]
                bare_qpg = bare_qpg[:,:,0]+bare_qpg[:,:,1]*I
                q_cutoff = np.abs(bare_qpg[0,int(Qpt)-1])

        return cls(lattice,Qpt,eigenvalues,l_residual,r_residual,spin_pol,q_cutoff=q_cutoff,car_qpoint=car_qpoint,table=table,eigenvectors=eigenvectors)

    @property
    def unique_vbands(self):
        return np.unique(self.table[:,1]-1)

    @property
    def unique_cbands(self):
        return np.unique(self.table[:,2]-1)

    @property
    def transitions_v_to_c(self):
        """Compute transitions from valence to conduction"""
        if hasattr(self,"_transitions_v_to_c"): return self._transitions_v_to_c
        uniq_v = self.unique_vbands
        uniq_c = self.unique_cbands
        transitions_v_to_c = dict([ ((v,c),[]) for v,c in product(uniq_v,uniq_c) ])

        #add elements to dictionary
        kidx = set()
        for eh,kvc in enumerate(self.table-1):
            k,v,c = kvc
            kidx.add(k)
            transitions_v_to_c[(v,c)].append((k,eh))
        self.nkpoints = len(kidx)

        #make an array 
        for t,v in list(transitions_v_to_c.items()):
            if len(np.array(v)):
                transitions_v_to_c[t] = np.array(v)
            else:
                del transitions_v_to_c[t]

        self._transitions_v_to_c = transitions_v_to_c 
        return transitions_v_to_c

    @property
    def nkpoints(self): return max(self.table[:,0])

    @property
    def nvbands(self): return len(self.unique_vbands)

    @property
    def ncbands(self): return len(self.unique_cbands)

    @property
    def nbands(self): return self.ncbands+self.nvbands

    @property
    def mband(self): return max(self.unique_cbands)+1
 
    @property
    def ntransitions(self): return len(self.table)

    @property
    def nexcitons(self): return len(self.eigenvalues)
    
    @property
    def start_band(self): return min(self.unique_vbands)

    def write_sorted(self,prefix='yambo'):
        """
        Write the sorted energies and intensities to a file
        """
        #get intensities
        eig = self.eigenvalues.real
        intensities = self.get_intensities()

        #get sorted energies
        sort_e, sort_i = self.get_sorted()     

        #write excitons sorted by energy
        with open('%s_E.dat'%prefix, 'w') as f:
            for e,n in sort_e:
                f.write("%3d %12.8lf %12.8e\n"%(n+1,e,intensities[n])) 

        #write excitons sorted by intensities
        with open('%s_I.dat'%prefix,'w') as f:
            for i,n in sort_i:
                f.write("%3d %12.8lf %12.8e\n"%(n+1,eig[n],i)) 

    def get_nondegenerate(self,eps=1e-4):
        """
        get a list of non-degenerate excitons
        """
        non_deg_e   = [0]
        non_deg_idx = [] 

        #iterate over the energies
        for n,e in enumerate(self.eigenvalues):
            if not np.isclose(e,non_deg_e[-1],atol=eps):
                non_deg_e.append(e)
                non_deg_idx.append(n)

        return np.array(non_deg_e[1:]), np.array(non_deg_idx)

    def get_intensities(self):
        """
        get the intensities of the excitons
        """
        intensities = self.l_residual*self.r_residual
        intensities /= np.max(intensities)
        return intensities

    def get_sorted(self):
        """
        Return the excitonic weights sorted according to energy and intensity
        """
        #get intensities
        eig = self.eigenvalues.real
        intensities = self.get_intensities()

        #list ordered with energy
        sort_e = sorted(zip(eig, list(range(self.nexcitons))))

        #list ordered with intensity
        sort_i = sorted(zip(intensities, list(range(self.nexcitons))),reverse=True)

        return sort_e, sort_i 

    def get_degenerate(self,index,eps=1e-4):
        """
        Get degenerate excitons
        
        Args:
            eps: maximum energy difference to consider the two excitons degenerate in eV
        """
        energy = self.eigenvalues[index-1]
        excitons = [] 
        for n,e in enumerate(self.eigenvalues):
            if np.isclose(energy,e,atol=eps):
                excitons.append(n+1)
        return excitons

    def exciton_bs(self,energies,path,excitons=(0,),debug=False):
        """
        Calculate exciton band-structure
            
            Arguments:
            energies -> can be an instance of YamboSaveDB or YamboQBDB
            path     -> path in reduced coordinates in which to plot the band structure
            exciton  -> exciton index to plot
            spin     -> ??
        """
        if self.eigenvectors is None:
            raise ValueError('This database does not contain Excitonic states,'
                              'please re-run the yambo BSE calculation with the WRbsWF option in the input file.')
        if isinstance(excitons, int):
            excitons = (excitons,)
        #get full kmesh
        kpoints = self.lattice.red_kpoints
        path = np.array(path)

        rep = list(range(-1,2))
        kpoints_rep, kpoints_idx_rep = replicate_red_kmesh(kpoints,repx=rep,repy=rep,repz=rep)
        band_indexes = get_path(kpoints_rep,path,debug=debug)
        band_kpoints = kpoints_rep[band_indexes] 
        band_indexes = kpoints_idx_rep[band_indexes]

        if debug:
            import matplotlib.pyplot as plt
            for i,k in zip(band_indexes,band_kpoints):
                x,y,z = k
                plt.text(x,y,i) 
            plt.scatter(kpoints_rep[:,0],kpoints_rep[:,1])
            plt.plot(path[:,0],path[:,1],c='r')
            plt.scatter(band_kpoints[:,0],band_kpoints[:,1])
            plt.show()
            exit()

        #get eigenvalues along the path
        if isinstance(energies,(YamboSaveDB,YamboElectronsDB)):
            #expand eigenvalues to the full brillouin zone
            # SPIN-UP CHANNEL ONLY. Check with BSE WFs
            energies = energies.eigenvalues[0,self.lattice.kpoints_indexes]
            
        elif isinstance(energies,YamboQPDB):
            #expand the quasiparticle energies to the bull brillouin zone
            pad_energies = energies.eigenvalues_qp[self.lattice.kpoints_indexes]
            min_band = energies.min_band
            nkpoints, nbands = pad_energies.shape
            energies = np.zeros([nkpoints,energies.max_band])
            energies[:,min_band-1:] = pad_energies 
        else:
            raise ValueError("Energies argument must be an instance of YamboSaveDB,"
                             "YamboElectronsDB or YamboQPDB. Got %s"%(type(energies)))

        weights = self.get_exciton_weights(excitons)      
        energies = energies[band_indexes]
        weights  = weights[band_indexes]

        #make top valence band to be zero
        energies -= max(energies[:,max(self.unique_vbands)])
        
        return np.array(band_kpoints), energies, weights 

    def magnon_bs(self,energies,path,excitons=(0,),debug=False):
        """
        Calculate exciton band-structure
            
            Arguments:
            energies -> can be an instance of YamboSaveDB or YamboQBDB
            path     -> path in reduced coordinates in which to plot the band structure
            exciton  -> exciton index to plot
        """
        if self.eigenvectors is None:
            raise ValueError('This database does not contain Excitonic states,'
                              'please re-run the yambo BSE calculation with the WRbsWF option in the input file.')
        if isinstance(excitons, int):
            excitons = (excitons,)
        #get full kmesh
        kpoints = self.lattice.red_kpoints
        path = np.array(path)

        rep = list(range(-1,2))
        kpoints_rep, kpoints_idx_rep = replicate_red_kmesh(kpoints,repx=rep,repy=rep,repz=rep)
        band_indexes = get_path(kpoints_rep,path)
        band_kpoints = kpoints_rep[band_indexes] 
        band_indexes = kpoints_idx_rep[band_indexes]

        if debug:
            for i,k in zip(band_indexes,band_kpoints):
                x,y,z = k
                plt.text(x,y,i) 
            plt.scatter(kpoints_rep[:,0],kpoints_rep[:,1])
            plt.plot(path[:,0],path[:,1],c='r')
            plt.scatter(band_kpoints[:,0],band_kpoints[:,1])
            plt.show()
            exit()
        print('self.nvbands')
        print(self.nvbands)
        print('self.ncbands')
        print(self.ncbands)
        exit()
        #get eigenvalues along the path
        if isinstance(energies,(YamboSaveDB,YamboElectronsDB)):
            #expand eigenvalues to the full brillouin zone
            # SPIN-UP Valence
            energies_v = energies.eigenvalues[0,self.lattice.kpoints_indexes,:self.nvbands]
            energies_c = energies.eigenvalues[1,self.lattice.kpoints_indexes,self.nvbands:(self.nvbands+self.ncbands)]


        elif isinstance(energies,YamboQPDB):
            #expand the quasiparticle energies to the bull brillouin zone
            pad_energies = energies.eigenvalues_qp[self.lattice.kpoints_indexes]
            min_band = energies.min_band
            nkpoints, nbands = pad_energies.shape
            energies = np.zeros([nkpoints,energies.max_band])
            energies[:,min_band-1:] = pad_energies 
        else:
            raise ValueError("Energies argument must be an instance of YamboSaveDB,"
                             "YamboElectronsDB or YamboQPDB. Got %s"%(type(energies)))

        weights = self.get_exciton_weights(excitons)      
        #print(energies.shape)
        #exit()
        energies = energies[band_indexes]
        weights  = weights[band_indexes]

        #make top valence band to be zero
        energies -= max(energies[:,max(self.unique_vbands)])
        
        return np.array(band_kpoints), energies, weights 


    def arpes_intensity(self,energies_db,path,excitons,ax):   #,size=1,space='bands',f=None,debug=False): later on
        size=1 # luego lo ponemos como input variable 
        n_excitons = len(excitons)
        #
        kpath   = path
        # kpoints IBZ
        kpoints = self.lattice.red_kpoints
        # array of high symmetry k-points
        path    = np.array(path.kpoints)

        # Expansion of IBZ kpoints to Path kpoints
        rep = list(range(-1,2))
        kpoints_rep, kpoints_idx_rep = replicate_red_kmesh(kpoints,repx=rep,repy=rep,repz=rep)
        band_indexes = get_path(kpoints_rep,path)
        band_kpoints = np.array(kpoints_rep[band_indexes])
        band_indexes = kpoints_idx_rep[band_indexes]

        # Eigenvalues Full BZ
        # Dimension nk_fbz x nbands
        energies = energies_db.eigenvalues[self.lattice.kpoints_indexes]

        # Calculate omega
        # omega_vk,lambda = e_(v,k-q) + omega_(lambda,q) only for q=0
        '''
        omega_vkl = np.zeros([self.nkpoints, self.nvbands,n_excitons])
        for i_l,exciton in enumerate(excitons):
            for i_k in range(self.nkpoints):
                for i_v in range(self.nvbands):
                    i_v2 = self.unique_vbands[i_v]
                    # omega_vk,lambda      = e_(v,k-q) + omega_(lambda,q)
                    omega_vkl[i_k,i_v,i_l] = energies[i_k,i_v2] + self.eigenvalues.real[exciton-1]

        '''
        omega_vkl = self.calculate_omega(energies,excitons)
        rho       = self.calculate_rho(excitons)
        # Calculate rho's
        # rho_vk = Sum_{c} |A_cvk|^2
#        rho = np.zeros([self.nkpoints, self.nvbands, n_excitons])


#        for i_exc, exciton in enumerate(excitons):
#            # get the eigenstate
#            eivec = self.eigenvectors[exciton-1]
#            for t,kvc in enumerate(self.table):
#                k,v,c = kvc[0:3]-1    # This is bug's source between yambo 4.4 and 5.0 check all this part of the class
#                i_v = v - self.nvbands                    # index de VB bands (start at 0)
#                i_c = c - self.ncbands - self.nvbands     # index de CB bands (start at 0)
#                rho[k,i_v,i_exc] += abs2(eivec[t])

        # Eigenvalues Path contains in Full BZ
        energies_path  = energies[band_indexes]
        rho_path       = rho[band_indexes]
        omega_vkl_path = omega_vkl[band_indexes]

        #make top valence band to be zero
        energies_path -= max(energies_path[:,max(self.unique_vbands)])

        plot_energies = energies_path[:,self.start_band:self.mband]
  
        # LDA or GW band structure
        ybs_bands = YambopyBandStructure(plot_energies, band_kpoints, kpath=kpath)


        # Intensity Plot
        print('shape energies_path')
        nkpoints_path=energies_path.shape[0]
        #exit()
        # Intensity histogram
        # I(k,omega_band)
        omega_band = np.arange(0.0,7.0,0.01)
        n_omegas = len(omega_band)
        Intensity = np.zeros([n_omegas,nkpoints_path]) 
        Im = 1.0j
           #for i_o in range(n_omegas):

        for i_o in range(n_omegas):
            for i_k in range(nkpoints_path):
                for i_v in range(self.nvbands):
                    for i_exc in range(n_excitons):
                        delta = 1.0/( omega_band[i_o] - omega_vkl_path[i_k,i_v,i_exc] + Im*0.2 )
                        Intensity[i_o,i_k] += rho_path[i_k,i_v,i_exc]*delta.imag

        distances = [0]
        distance = 0
        for nk in range(1,nkpoints_path):
            distance += np.linalg.norm(band_kpoints[nk]-band_kpoints[nk-1])
            distances.append(distance)
        distances = np.array(distances)
        X, Y = np.meshgrid(distances, omega_band)
        import matplotlib.pyplot as plt
        #plt.imshow(Intensity, interpolation='bilinear',cmap='viridis_r')
        plt.pcolor(X, Y, Intensity,cmap='viridis_r',shading='auto')
        # Excitonic Band Structure
        for i_v in range(self.nvbands):
            for i_exc in range(n_excitons):
                plt.plot(distances,omega_vkl_path[:,i_v,i_exc],color='w',lw=0.5) 
        # Electronic Band Structure
       
        for i_b in range(energies_db.nbands):
            plt.plot(distances,energies_path[:,i_b],lw=1.0,color='r')
        plt.xlim((distances[0],distances[-1]))
        plt.ylim((-5,10))
        plt.show()
        exit()

        # ARPES band structure
        ybs_omega = []
        for i_exc in range(n_excitons):
            plot_omega    = omega_vkl_path[:,:,i_exc]
            plot_rho      = rho_path[:,:,i_exc]
            size *= 1.0/np.max(plot_rho)
            ybs_omega.append( YambopyBandStructure(plot_omega, band_kpoints, weights=plot_rho, kpath=kpath, size=size) )

        # Plot bands
        ybs_bands.plot_ax(ax,color_bands='black',lw_label=2)

        for ybs in ybs_omega:
            ybs.plot_ax(ax,color_bands='black',lw_label=0.1)

        return rho

    def calculate_omega(self,energies,excitons):
        """ Calculate:
            omega_vk,lambda = e_(v,k-q) + omega_(lambda,q) only for q=0
        """

        n_excitons = len(excitons)
        omega_vkl = np.zeros([self.nkpoints, self.nvbands,n_excitons])
        for i_l,exciton in enumerate(excitons):
            for i_k in range(self.nkpoints):
                for i_v in range(self.nvbands):
                    i_v2 = self.unique_vbands[i_v]
                    # omega_vk,lambda      = e_(v,k-q) + omega_(lambda,q)
                    omega_vkl[i_k,i_v,i_l] = energies[i_k,i_v2] + self.eigenvalues.real[exciton-1]
         
        return omega_vkl

    def calculate_rho(self,excitons):
        """ Calculate:
            rho_vkl = Sum_{c} |A_cvk,l|^2
        """
        n_excitons = len(excitons)
        print('self.nkpoints, self.nvbands, n_excitons')
        print(self.nkpoints, self.nvbands, n_excitons)
        print('self.unique_vbands')
        print(self.unique_vbands)
        print('self.unique_cbands')
        print(self.unique_cbands)
        rho = np.zeros([self.nkpoints, self.nvbands, n_excitons])
        for i_exc, exciton in enumerate(excitons):
            # get the eigenstate
            eivec = self.eigenvectors[exciton-1]
            for t,kvc in enumerate(self.table):
                k,v,c = kvc[0:3]-1    # This is bug's source between yambo 4.4 and 5.0 check all this part of the class
                i_v = v - self.unique_vbands[0] # index de VB bands (start at 0)
                #i_c = c - self.unique_cbands[0] # index de CB bands (start at 0)
                rho[k,i_v,i_exc] += abs2(eivec[t])

        return rho

    #def arpes_interpolate(self,energies,path,excitons,lpratio=5,f=None,size=1,verbose=True,**kwargs):
    def arpes_intensity_interpolated(self,energies_db,path,excitons,lpratio=5,f=None,size=1,verbose=True,**kwargs):
        """ 
            Interpolate arpes bandstructure using SKW interpolation from Abipy (version 1)
            Change to the Fourier Transform Interpolation
            DFT energies == energies_db
            All is done internally. No use of the bandstructure class
            (something to change)
        """
        from abipy.core.skw import SkwInterpolator
        Im = 1.0j # Imaginary
        
        # Number of exciton states
        n_excitons = len(excitons)

        # Options kwargs

        # Alignment of the Bands Top Valence
        fermie      = kwargs.pop('fermie',0)
        # Parameters ARPES Intensity
        omega_width = kwargs.pop('omega_width',0)
        omega_1     = kwargs.pop('omega_1',0)
        omega_2     = kwargs.pop('omega_2',0)
        omega_step  = kwargs.pop('omega_step',0)
        omega_band  = np.arange(omega_1,omega_2,omega_step)
        n_omegas = len(omega_band)
        cmap_name   = kwargs.pop('cmap_name',0)
        scissor    = kwargs.pop('scissor',0)
       
        # Lattice and Symmetry Variables
        lattice = self.lattice
        cell = (lattice.lat, lattice.red_atomic_positions, lattice.atomic_numbers)

        symrel = [sym for sym,trev in zip(lattice.sym_rec_red,lattice.time_rev_list) if trev==False ]
        time_rev = True

        nelect = 0  # Why?

        # DFT Eigenvalues FBZ
        energies = energies_db.eigenvalues[0,self.lattice.kpoints_indexes] #SPIN-UP
        # Rho FBZ
        rho      = self.calculate_rho(excitons)
        if f: rho = f(rho)
        # Omega FBZ
        omega    = self.calculate_omega(energies,excitons)

        size *= 1.0/np.max(rho)

        ibz_nkpoints = max(lattice.kpoints_indexes)+1
        kpoints = lattice.red_kpoints

        #map from bz -> ibz:
        ibz_rho     = np.zeros([ibz_nkpoints,self.nvbands,n_excitons])
        ibz_kpoints = np.zeros([ibz_nkpoints,3])
        ibz_omega   = np.zeros([ibz_nkpoints,self.nvbands,n_excitons])
        for idx_bz,idx_ibz in enumerate(lattice.kpoints_indexes):
            ibz_rho[idx_ibz,:,:]   = rho[idx_bz,:,:] 
            ibz_kpoints[idx_ibz]   = lattice.red_kpoints[idx_bz]
            ibz_omega[idx_ibz,:,:] = omega[idx_bz,:,:] 

        #get DFT or GW eigenvalues
        if isinstance(energies_db,(YamboSaveDB,YamboElectronsDB)):
            ibz_energies = energies_db.eigenvalues[0,:,self.start_band:self.mband] #spin-up
        elif isinstance(energies_db,YamboQPDB):   # Check this works !!!!
            ibz_energies = energies_db.eigenvalues_qp
        else:
            raise ValueError("Energies argument must be an instance of YamboSaveDB,"
                             "YamboElectronsDB or YamboQPDB. Got %s"%(type(energies)))

        # set k-path
        kpoints_path = path.get_klist()[:,:3]
        distances = calculate_distances(kpoints_path)
        nkpoints_path = kpoints_path.shape[0]

        na = np.newaxis
        rho_path   = np.zeros([1, nkpoints_path, self.nvbands, n_excitons])
        omega_path = np.zeros([1, nkpoints_path, self.nvbands, n_excitons])

        for i_exc in range(n_excitons):

            # interpolate rho along the k-path
            skw_rho   = SkwInterpolator(lpratio,ibz_kpoints,ibz_rho[na,:,:,i_exc],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
            rho_path[0,:,:,i_exc] = skw_rho.interp_kpts(kpoints_path).eigens

            # interpolate omega along the k-path
            skw_omega = SkwInterpolator(lpratio,ibz_kpoints,ibz_omega[na,:,:,i_exc],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
            omega_path[0,:,:,i_exc] = skw_omega.interp_kpts(kpoints_path).eigens

        # interpolate energies
        skw_energie = SkwInterpolator(lpratio,ibz_kpoints,ibz_energies[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        energies_path = skw_energie.interp_kpts(kpoints_path).eigens

        top_valence_band = np.max(energies_path[0,:,0:self.nvbands])
        omega_path    = omega_path - top_valence_band
        energies_path = energies_path - top_valence_band

        import matplotlib.pyplot as plt

        # I(k,omega_band)
        Intensity = np.zeros([n_omegas,nkpoints_path]) 
         
        for i_exc in range(n_excitons):
            for i_o in range(n_omegas):
                for i_k in range(nkpoints_path):
                    for i_v in range(self.nvbands):
                        delta = 1.0/( omega_band[i_o] - omega_path[0, i_k, i_v, i_exc] + Im*omega_width ) # check this
                        Intensity[i_o,i_k] += rho_path[0, i_k, i_v, i_exc]*delta.imag

        X, Y = np.meshgrid(distances, omega_band)
        import matplotlib.pyplot as plt

        # Plot I(k,w)
        plt.pcolor(X, Y, Intensity,cmap=cmap_name,shading='auto')


        # Plot Excitonic Energies
        #for i_exc in range(n_excitons):
        #    for i_v in range(self.nvbands):
        #        plt.plot(distances,omega_path[0,:,i_v,i_exc],color='white',lw=0.5)

        # Plot Valence Band Energies
        #for i_b in range(energies_path.shape[2]):
        for i_b in range(self.nvbands):
            plt.plot(distances,energies_path[0,:,i_b],lw=1.0,color='white')
        for i_b in range(self.ncbands):
            plt.plot(distances,energies_path[0,:,i_b+self.nvbands]+scissor,lw=1.0,color='white')
            #plt.plot(distances,energies_path[0,:,i_b+9],lw=0.5,color='r')

        plt.xlim((distances[0],distances[-1]))
        plt.ylim((omega_1,omega_2-omega_width))

        #plt.axhline(np.max(energies_path[0,:,0:self.nvbands]),c='white')
        for kpoint, klabel, distance in path:
            plt.axvline(distance,c='w')
        plt.xticks(path.distances,path.klabels)
        plt.show()

        #create band-structure object
        #exc_bands = YambopyBandStructure(energies[0],kpoints_path,kpath=path,weights=exc_weights[0],size=size,**kwargs)
        #exc_bands.set_fermi(self.nvbands)
        #exit()
        #return exc_bands
        return 

    def get_exciton_weights(self,excitons):
        """get weight of state in each band"""
        weights = np.zeros([self.nkpoints,self.mband])
        for exciton in excitons:
            #get the eigenstate
            eivec = self.eigenvectors[exciton-1]

            #add weights
            sum_weights = 0
            for t,kcv in enumerate(self.table):
                k,c,v = kcv[0:3]-1    # This is bug's source between yambo 4.4 and 5.0 
                this_weight = abs2(eivec[t])
                weights[k,c] += this_weight
                weights[k,v] += this_weight
                sum_weights += this_weight
            if abs(sum_weights - 1) > 1e-3: raise ValueError('Excitonic weights does not sum to 1 but to %lf.'%sum_weights)
 
        return weights
    
    def get_exciton_total_weights(self,excitons):
        """get weight of state in each band"""
        total_weights = np.zeros(self.nkpoints)
        for exciton in excitons:
            #get the eigenstate
            eivec = self.eigenvectors[exciton-1]
            #add weights
            sum_weights = 0
            for t,kcv in enumerate(self.table):
                k,c,v = kcv[0:3]
                total_weights[k-1] += abs2(eivec[t])
            if abs(sum(total_weights) - 1) > 1e-3: raise ValueError('Excitonic weights does not sum to 1 but to %lf.'%sum_weights)
 
        return total_weights

    def get_exciton_transitions(self,excitons):
        """get weight of state in each band"""
        # Double check the part of the array w_k_v_to_c
        # We should comment more this part
        #weights = np.zeros([self.nkpoints,self.mband])
        w_k_v_to_c = np.zeros([self.nkpoints,self.nvbands,self.ncbands])
        v_min = self.unique_vbands[0]
        c_min = self.unique_cbands[0]
        for exciton in excitons:
            #get the eigenstate
            eivec = self.eigenvectors[exciton-1]
            #add weights
            #sum_weights = 0
            for t,kcv in enumerate(self.table):
                k,c,v = kcv-1
                #k,v,c = kcv-1                                 # bug?? Double-check
                this_weight = abs2(eivec[t])
                w_k_v_to_c[k,v-v_min,c-c_min] = this_weight   # new
            #if abs(sum_weights - 1) > 1e-3: raise ValueError('Excitonic weights does not sum to 1 but to %lf.'%sum_weights)
 
        #return weights, w_k_v_to_c
        return w_k_v_to_c

    def get_exciton_2D(self,excitons,f=None):
        """get data of the exciton in 2D"""
        weights = self.get_exciton_weights(excitons)
        #sum all the bands
        weights_bz_sum = np.sum(weights,axis=1)
        if f: weights_bz_sum = f(weights_bz_sum)

        kmesh_full, kmesh_idx = replicate_red_kmesh(self.lattice.red_kpoints,repx=range(-1,2),repy=range(-1,2))
        x,y = red_car(kmesh_full,self.lattice.rlat)[:,:2].T
        weights_bz_sum = weights_bz_sum[kmesh_idx]
        return x,y,weights_bz_sum
 
    def plot_exciton_2D_ax(self,ax,excitons,f=None,mode='hexagon',limfactor=0.8,**kwargs):
        """
        Plot the exciton weights in a 2D Brillouin zone
       
           Arguments:
            excitons -> list of exciton indexes to plot
            f -> function to apply to the exciton weights. Ex. f=log will compute the 
                 log of th weight to enhance the small contributions
            mode -> possible values are 'hexagon'/'square' to use hexagons/squares as markers for the 
                    weights plot and 'rbf' to interpolate the weights using radial basis functions.
            limfactor -> factor of the lattice parameter to choose the limits of the plot 
            scale -> size of the markers
        """
        x,y,weights_bz_sum = self.get_exciton_2D(excitons,f=f)

        #filter points outside of area
        lim = np.max(self.lattice.rlat)*limfactor
        dlim = lim*1.1
        filtered_weights = [[xi,yi,di] for xi,yi,di in zip(x,y,weights_bz_sum) if -dlim<xi and xi<dlim and -dlim<yi and yi<dlim]
        x,y,weights_bz_sum = np.array(filtered_weights).T
        # Add contours of BZ
        ax.add_patch(BZ_Wigner_Seitz(self.lattice))

        #plotting
        if mode == 'hexagon': 
            scale = kwargs.pop('scale',1)
            ax.scatter(x,y,s=scale,marker='H',c=weights_bz_sum,rasterized=True,**kwargs)
            ax.set_xlim(-lim,lim)
            ax.set_ylim(-lim,lim)
        elif mode == 'square': 
            scale = kwargs.pop('scale',1)
            ax.scatter(x,y,s=scale,marker='s',c=weights_bz_sum,rasterized=True,**kwargs)
            ax.set_xlim(-lim,lim)
            ax.set_ylim(-lim,lim)
        elif mode == 'rbf':
            from scipy.interpolate import Rbf
            npts = kwargs.pop('npts',100)
            interp_method = kwargs.pop('interp_method','bicubic')
            rbfi = Rbf(x,y,weights_bz_sum,function='linear')
            x = y = np.linspace(-lim,lim,npts)
            weights_bz_sum = np.zeros([npts,npts])
            for col in range(npts):
                weights_bz_sum[:,col] = rbfi(x,np.ones_like(x)*y[col])
            # NB we have to take the transpose of the imshow data to get the correct plot
            ax.imshow(weights_bz_sum.T,interpolation=interp_method,extent=[-lim,lim,-lim,lim])
        title = kwargs.pop('title',str(excitons))
        
        ax.set_title(title)
        ax.set_aspect('equal')
        ax.set_xticks([])
        ax.set_yticks([])

        return ax

    def plot_nbrightest_2D(self,emin=0,emax=10,estep=0.001,broad=0.1,
                           mode='rbf',scale=3,nrows=2,ncols=2,eps=1e-5):
        """
        Create a plot with chi and vertical bars for the brightest excitons
        Also plot the 2D wavefunctions of the brightest excitons.

          Arguments:
            emin,emax -> minimum and maximum energy range to plot chi
            estep -> energy step to plot chi
            broad -> broadening of the exciton peaks
            mode -> possible values are 'hexagon' to use hexagons as markers for the 
                    weights plot and 'rbf' to interpolate the weights using radial basis functions.
            scale -> size of the markers
            nrows,ncols -> number of rows and colums for the 2D plots (default: 2x2)
            eps -> threshold to find degenerate states
        """
        import matplotlib.pyplot as plt
        figexc = plt.figure()
        n_brightest = nrows*ncols
        figchi = self.plot_chi(emin=emin,emax=emax,estep=estep,broad=broad,n_brightest=n_brightest,show=False)
        #plot vertical bar on the brightest excitons
        exc_e,exc_i = self.get_sorted()
        sorted_exc = sorted(exc_i[:n_brightest],key = lambda x: x[1])
        for n,(i,idx) in enumerate(sorted_exc):
            ax = figexc.add_subplot(nrows,ncols,n+1)
            excitons = self.get_degenerate(idx,eps)
            self.plot_exciton_2D_ax(ax,excitons,scale=scale,mode=mode)
        return figchi,figexc

    def get_exciton_bs(self,energies_db,path,excitons,size=1,space='bands',f=None,debug=False):
        """
        Get a YambopyBandstructure object with the exciton band-structure
        
            Arguments:
            ax          -> axis extance of matplotlib to add the plot to
            lattice     -> Lattice database
            energies_db -> Energies database, can be either a SaveDB or QPDB
            path        -> Path in the brillouin zone
        """
        from qepy.lattice import Path
        if not isinstance(path,Path): 
            raise ValueError('Path argument must be a instance of Path. Got %s instead'%type(path))
    
        if space == 'bands':
            if self.spin_pol=='no':
               bands_kpoints, energies, weights = self.exciton_bs(energies_db, path.kpoints, excitons, debug)
               nkpoints = len(bands_kpoints)
               plot_energies = energies[:,self.start_band:self.mband]
               plot_weights  = weights[:,self.start_band:self.mband]
        #    elif spin_pol=='pol':
               
        else:
            raise NotImplementedError('TODO')
            eh_size = len(self.unique_vbands)*len(self.unique_cbands)
            nkpoints = len(bands_kpoints)
            plot_energies = np.zeros([nkpoints,eh_size])
            plot_weights = np.zeros([nkpoints,eh_size])
            for eh,(v,c) in enumerate(product(self.unique_vbands,self.unique_cbands)):
                plot_energies[:,eh] = energies[:,c]-energies[:,v]
                plot_weights[:,eh] = weights[:,c] 

        if f: plot_weights = f(plot_weights)
        size *= 1.0/np.max(plot_weights)
        ybs = YambopyBandStructure(plot_energies, bands_kpoints, weights=plot_weights, kpath=path, size=size)
        return ybs

    def get_magnon_bs(self,energies_db,path,excitons,size=1,space='bands',f=None,debug=False):
        """
        Get a YambopyBandstructure object with the exciton band-structure
        
            Arguments:
            ax          -> axis extance of matplotlib to add the plot to
            lattice     -> Lattice database
            energies_db -> Energies database, can be either a SaveDB or QPDB
            path        -> Path in the brillouin zone
        """
        from qepy.lattice import Path
        if not isinstance(path,Path): 
            raise ValueError('Path argument must be a instance of Path. Got %s instead'%type(path))
    
        if space == 'bands':
            bands_kpoints, energies, weights = self.magnon_bs(energies_db, path.kpoints, excitons, debug)
            nkpoints = len(bands_kpoints)
            plot_energies = energies[:,self.start_band:self.mband]
            plot_weights  = weights[:,self.start_band:self.mband]
        else:
            raise NotImplementedError('TODO')
            eh_size = len(self.unique_vbands)*len(self.unique_cbands)
            nkpoints = len(bands_kpoints)
            plot_energies = np.zeros([nkpoints,eh_size])
            plot_weights = np.zeros([nkpoints,eh_size])
            for eh,(v,c) in enumerate(product(self.unique_vbands,self.unique_cbands)):
                plot_energies[:,eh] = energies[:,c]-energies[:,v]
                plot_weights[:,eh] = weights[:,c] 

        if f: plot_weights = f(plot_weights)
        size *= 1.0/np.max(plot_weights)
        ybs = YambopyBandStructure(plot_energies, bands_kpoints, weights=plot_weights, kpath=path, size=size)
        return ybs

    def plot_exciton_bs_ax(self,ax,energies_db,path,excitons,size=1,space='bands',f=None,debug=None):
        ybs = self.get_exciton_bs(energies_db,path,excitons,size=size,space=space,f=f,debug=debug)
        return ybs.plot_ax(ax) 

    @add_fig_kwargs
    def plot_exciton_bs(self,energies_db,path,excitons,size=1,space='bands',f=None,debug=False,**kwargs):
        import matplotlib.pyplot as plt
        fig = plt.figure()
        ax = fig.add_subplot(1,1,1)
        self.plot_exciton_bs_ax(ax,energies_db,path,excitons,size=size,space=space,f=f,debug=debug)
        return fig

    def interpolate(self,energies,path,excitons,lpratio=5,f=None,size=1,verbose=True,**kwargs):
        """ Interpolate exciton bandstructure using SKW interpolation from Abipy
        """
        from abipy.core.skw import SkwInterpolator

        if verbose:
            print("This interpolation is provided by the SKW interpolator implemented in Abipy")

        lattice = self.lattice
        cell = (lattice.lat, lattice.red_atomic_positions, lattice.atomic_numbers)
        nelect = 0
        # Here there is something strange...

        fermie = kwargs.pop('fermie',0)
        ##
        symrel = [sym for sym,trev in zip(lattice.sym_rec_red,lattice.time_rev_list) if trev==False ]
        time_rev = True
 
        weights = self.get_exciton_weights(excitons)
        print('weights.shape')
        print(weights.shape)
        weights = weights[:,self.start_band:self.mband]
        print('self.start_band')
        print(self.start_band)
        print('self.mband')
        print(self.mband)
        if f: weights = f(weights)
        size *= 1.0/np.max(weights)
        ibz_nkpoints = max(lattice.kpoints_indexes)+1
        kpoints = lattice.red_kpoints

        #map from bz -> ibz:
        # bug here? it is self.mband, but why?
        ibz_weights = np.zeros([ibz_nkpoints,self.mband-self.start_band]) 
        print('ibz_weights.shape')
        print(ibz_weights.shape)
        print(self.nbands)
        print(self.mband)
        #exit()
        ibz_kpoints = np.zeros([ibz_nkpoints,3])
        for idx_bz,idx_ibz in enumerate(lattice.kpoints_indexes):
            ibz_weights[idx_ibz,:] = weights[idx_bz,:] 
            ibz_kpoints[idx_ibz] = lattice.red_kpoints[idx_bz]
        #get eigenvalues along the path
        if isinstance(energies,(YamboSaveDB,YamboElectronsDB)):
            #ibz_energies = energies.eigenvalues[:,self.start_band:self.mband] Old version
            ibz_energies = energies.eigenvalues[0,:,self.start_band:self.mband] # SPIN-UP channel
        elif isinstance(energies,YamboQPDB):
            ibz_energies = energies.eigenvalues_qp # to be done for spin-UP channel
        else:
            raise ValueError("Energies argument must be an instance of YamboSaveDB,"
                             "YamboElectronsDB or YamboQPDB. Got %s"%(type(energies)))

        #interpolate energies
        na = np.newaxis
        skw = SkwInterpolator(lpratio,ibz_kpoints,ibz_energies[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        kpoints_path = path.get_klist()[:,:3]
        energies = skw.interp_kpts(kpoints_path).eigens
        #interpolate weights
        na = np.newaxis
        skw = SkwInterpolator(lpratio,ibz_kpoints,ibz_weights[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        kpoints_path = path.get_klist()[:,:3]
        exc_weights = skw.interp_kpts(kpoints_path).eigens

        #create band-structure object
        exc_bands = YambopyBandStructure(energies[0],kpoints_path,kpath=path,weights=exc_weights[0],size=size,**kwargs)
        exc_bands.set_fermi(self.nvbands)

        return exc_bands

    def interpolate_transitions(self,energies,path,excitons,lpratio=5,f=None,size=1,verbose=True,**kwargs):
        """ Interpolate exciton bandstructure using SKW interpolation from Abipy
        """
        from abipy.core.skw import SkwInterpolator

        if verbose:
            print("This interpolation is provided by the SKW interpolator implemented in Abipy")

        lattice = self.lattice
        cell = (lattice.lat, lattice.red_atomic_positions, lattice.atomic_numbers)
        nelect = 0
        # Here there is something strange...
        fermie = kwargs.pop('fermie',0)
        ##
        symrel = [sym for sym,trev in zip(lattice.sym_rec_red,lattice.time_rev_list) if trev==False ]
        time_rev = True

        #vmin, vmax = self.unique_vbands[0], self.unique_vbands[1]
        #cmin, cmax = self.unique_cbands[0], self.unique_cbands[1]

        transitions = self.get_exciton_transitions(excitons)
        transitions = transitions[:,:,:]

        ibz_nkpoints = max(lattice.kpoints_indexes)+1
        kpoints = lattice.red_kpoints

        #map from bz -> ibz:
        ibz_transitions = np.zeros([ibz_nkpoints,self.nvbands,self.ncbands])
        ibz_kpoints = np.zeros([ibz_nkpoints,3])
        for idx_bz,idx_ibz in enumerate(lattice.kpoints_indexes):
            ibz_transitions[idx_ibz,:,:] = transitions[idx_bz,:,:] 
            ibz_kpoints[idx_ibz] = lattice.red_kpoints[idx_bz]

        #get eigenvalues along the path
        if isinstance(energies,(YamboSaveDB,YamboElectronsDB)):
            ibz_energies = energies.eigenvalues[:,self.start_band:self.mband]
        elif isinstance(energies,YamboQPDB):
            ibz_energies = energies.eigenvalues_qp
        else:
            raise ValueError("Energies argument must be an instance of YamboSaveDB,"
                             "YamboElectronsDB or YamboQPDB. Got %s"%(type(energies)))

        #interpolate energies
        na = np.newaxis
        skw = SkwInterpolator(lpratio,ibz_kpoints,ibz_energies[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        kpoints_path = path.get_klist()[:,:3]
        energies = skw.interp_kpts(kpoints_path).eigens
     
        #interpolate transitions
        na = np.newaxis
        skw = SkwInterpolator(lpratio,ibz_kpoints,ibz_transitions[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        kpoints_path = path.get_klist()[:,:3]
        exc_transitions = skw.interp_kpts(kpoints_path).eigens

        print(exc_transitions.shape)
        exit()

        #create band-structure object
        exc_bands = YambopyBandStructure(energies[0],kpoints_path,kpath=path,weights=exc_weights[0],size=size,**kwargs)
        exc_bands.set_fermi(self.nvbands)

        return exc_transitions

    def interpolate_spin(self,energies,spin_proj,path,excitons,lpratio=5,f=None,size=1,verbose=True,**kwargs):
        """ Interpolate exciton bandstructure using SKW interpolation from Abipy
        """
        from abipy.core.skw import SkwInterpolator

        if verbose:
            print("This interpolation is provided by the SKW interpolator implemented in Abipy")

        lattice = self.lattice
        cell = (lattice.lat, lattice.red_atomic_positions, lattice.atomic_numbers)
        nelect = 0
        # Here there is something strange...

        fermie = kwargs.pop('fermie',0)
        ##
        symrel = [sym for sym,trev in zip(lattice.sym_rec_red,lattice.time_rev_list) if trev==False ]
        time_rev = True
 
        weights = self.get_exciton_weights(excitons)
        weights = weights[:,self.start_band:self.mband]
        if f: weights = f(weights)
        size *= 1.0/np.max(weights)
        ibz_nkpoints = max(lattice.kpoints_indexes)+1
        kpoints = lattice.red_kpoints

        #map from bz -> ibz:
        print("ibz_nkpoints")
        print(ibz_nkpoints)
        print("weights.shape")
        print(weights.shape)
        print(self.unique_vbands)
        print(self.unique_cbands)
        v_1 = self.unique_vbands[ 0]
        v_2 = self.unique_cbands[-1] + 1
        #exit()
        ibz_weights = np.zeros([ibz_nkpoints,self.nbands])
        ibz_kpoints = np.zeros([ibz_nkpoints,3])
        ibz_spin    = np.zeros([ibz_nkpoints,self.nbands])
        for idx_bz,idx_ibz in enumerate(lattice.kpoints_indexes):
            ibz_weights[idx_ibz,:] = weights[idx_bz,:] 
            ibz_kpoints[idx_ibz]   = lattice.red_kpoints[idx_bz]
            ibz_spin[idx_ibz,:]    = spin_proj[idx_bz,v_1:v_2]
        #get eigenvalues along the path
        if isinstance(energies,(YamboSaveDB,YamboElectronsDB)):
            ibz_energies = energies.eigenvalues[:,self.start_band:self.mband]
        elif isinstance(energies,YamboQPDB):
            ibz_energies = energies.eigenvalues_qp
        else:
            raise ValueError("Energies argument must be an instance of YamboSaveDB,"
                             "YamboElectronsDB or YamboQPDB. Got %s"%(type(energies)))

        #interpolate energies
        na = np.newaxis
        print("na")
        print(na)
        skw = SkwInterpolator(lpratio,ibz_kpoints,ibz_energies[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        kpoints_path = path.get_klist()[:,:3]
        energies = skw.interp_kpts(kpoints_path).eigens
     
        #interpolate weights
        na = np.newaxis
        skw = SkwInterpolator(lpratio,ibz_kpoints,ibz_weights[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        kpoints_path = path.get_klist()[:,:3]
        exc_weights = skw.interp_kpts(kpoints_path).eigens

        #interpolate spin projection
        na = np.newaxis
        print("na")
        print(na)
        skw = SkwInterpolator(lpratio,ibz_kpoints,ibz_spin[na,:,:],fermie,nelect,cell,symrel,time_rev,verbose=verbose)
        kpoints_path = path.get_klist()[:,:3]
        spin_inter   = skw.interp_kpts(kpoints_path).eigens
        print("spin_inter")
        print(spin_inter)

        #create band-structure object
        exc_bands = YambopyBandStructure(energies[0],kpoints_path,kpath=path,weights=exc_weights[0],spin_proj=spin_inter[0],size=size,**kwargs)
        exc_bands.set_fermi(self.nvbands)

        return exc_bands
 
    def get_amplitudes_phases(self,excitons=(0,),repx=list(range(1)),repy=list(range(1)),repz=list(range(1))):
        """ get the excitonic amplitudes and phases
        """
        if self.eigenvectors is None:
            raise ValueError('This database does not contain Excitonic states,'
                             'please re-run the yambo BSE calculation with the WRbsWF option in the input file.')
        if isinstance(excitons, int):
            excitons = (excitons,)
       
        car_kpoints = self.lattice.car_kpoints
        nkpoints = len(car_kpoints)
        print(nkpoints)
        amplitudes = np.zeros([nkpoints])
        phases     = np.zeros([nkpoints],dtype=np.complex64)
        for exciton in excitons:
            #the the eigenstate
            eivec = self.eigenvectors[exciton-1]
           
            total = 0
            for eh,kvc in enumerate(self.table):
                ikbz, v, c = kvc-1
                Acvk = eivec[eh]
                phases[ikbz]     += Acvk
                amplitudes[ikbz] += np.abs(Acvk)

        #replicate kmesh
        red_kmesh,kindx = replicate_red_kmesh(self.lattice.red_kpoints,repx=repx,repy=repy,repz=repz)
        car_kpoints = red_car(red_kmesh,self.lattice.rlat)

        return car_kpoints, amplitudes[kindx], np.angle(phases)[kindx]

    def get_chi(self,dipoles=None,dir=0,emin=0,emax=10,estep=0.01,broad=0.1,q0norm=1e-5, nexcitons='all',spin_degen=2,verbose=0,**kwargs):
        """
        Calculate the dielectric response function using excitonic states
        """
        if nexcitons == 'all': nexcitons = self.nexcitons

        #energy range
        w = np.arange(emin,emax,estep,dtype=np.float32)
        nenergies = len(w)
        
        if verbose:
            print("energy range: %lf -> +%lf -> %lf "%(emin,estep,emax))
            print("energy steps: %lf"%nenergies)

        #initialize the susceptibility intensity
        chi = np.zeros([len(w)],dtype=np.complex64)

        if dipoles is None:
            #get dipole
            EL1 = self.l_residual
            EL2 = self.r_residual
        else:
            #calculate exciton-light coupling
            if verbose: print("calculate exciton-light coupling")
            EL1,EL2 = self.project1(dipoles.dipoles[:,dir],nexcitons) 

        if isinstance(broad,float): broad = [broad]*nexcitons

        if isinstance(broad,tuple): 
            broad_slope = broad[1]-broad[0]
            min_exciton = np.min(self.eigenvalues.real)
            broad = [ broad[0]+(es-min_exciton)*broad_slope for es in self.eigenvalues[:nexcitons].real]

        if "gaussian" in broad or "lorentzian" in broad:
            i = broad.find(":")
            if i != -1:
                value, eunit = broad[i+1:].split()
                if eunit == "eV": sigma = float(value)
                else: raise ValueError('Unknown unit %s'%eunit)

            f = gaussian if "gaussian" in broad else lorentzian
            broad = np.zeros([nexcitons])
            for s in range(nexcitons):
                es = self.eigenvalues[s].real
                broad += f(self.eigenvalues.real,es,sigma)
            broad = 0.1*broad/nexcitons

        #iterate over the excitonic states
        for s in range(nexcitons):
            #get exciton energy
            es = self.eigenvalues[s]
 
            #calculate the green's functions
            G1 = -1/(   w - es + broad[s]*I)
            G2 = -1/( - w - es - broad[s]*I)

            r = EL1[s]*EL2[s]
            chi += r*G1 + r*G2

        #dimensional factors
        if not self.Qpt=='1': q0norm = 2*np.pi*np.linalg.norm(self.car_qpoint)
        if self.q_cutoff is not None: q0norm = self.q_cutoff

        d3k_factor = self.lattice.rlat_vol/self.lattice.nkpoints
        cofactor = ha2ev*spin_degen/(2*np.pi)**3 * d3k_factor * (4*np.pi)  / q0norm**2
        
        chi = 1. + chi*cofactor #We are actually computing the epsilon, not the chi.

        return w,chi

    def plot_chi_ax(self,ax,reim='im',n_brightest=-1,**kwargs):
        """Plot chi on a matplotlib axes"""
        w,chi = self.get_chi(**kwargs)
        #cleanup kwargs variables
        cleanup_vars = ['dipoles','dir','emin','emax','estep','broad',
                        'q0norm','nexcitons','spin_degen','verbose']
        for var in cleanup_vars: kwargs.pop(var,None)
        if 're' in reim: ax.plot(w,chi.real,**kwargs)
        if 'im' in reim: ax.plot(w,chi.imag,**kwargs)
        ax.set_ylabel('$Im(\chi(\omega))$')
        ax.set_xlabel('Energy (eV)')
        #plot vertical bar on the brightest excitons
        if n_brightest>-1:
            exc_e,exc_i = self.get_sorted()
            for i,idx in exc_i[:n_brightest]:
                exciton_energy,idx = exc_e[idx]
                ax.axvline(exciton_energy,c='k')
                ax.text(exciton_energy,0.1,idx,rotation=90)
        return w,chi

    @add_fig_kwargs
    def plot_chi(self,n_brightest=-1,**kwargs):
        """Produce a figure with chi"""
        import matplotlib.pyplot as plt
        fig = plt.figure()
        ax = fig.add_subplot(1,1,1)
        self.plot_chi_ax(ax,n_brightest=n_brightest,**kwargs)
        return fig

    def save_chi(self,filename,**kwargs):
        """Compute chi and dump it to file"""
        w,chi = self.get_chi(**kwargs)
        np.savetxt(filename,np.array([w,chi.imag,chi.real]).T)

    def get_string(self,mark="="):
        lines = []; app = lines.append
        app( marquee(self.__class__.__name__,mark=mark) )
        app( "BSE solved at Q:            %s"%self.Qpt )
        app( "number of excitons:         %d"%self.nexcitons )
        if self.table is not None: 
            app( "number of transitions:      %d"%self.ntransitions )
            app( "number of kpoints:          %d"%self.nkpoints  )
            app( "number of valence bands:    %d"%self.nvbands )
            app( "number of conduction bands: %d"%self.ncbands )
        return '\n'.join(lines)
    
    def __str__(self):
        return self.get_string()
