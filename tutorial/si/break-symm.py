##############################################################################
#
# Author: Alejandro Molina-Sanchez
# Run real-time simulations with yambo
# 
# Warning: Real-time simulations requires several data folders for running
# properly. Before using this scripts compulsively is recommended
# to understand the different run levels.
#
# This script breaks the symmetries of a given nscf run and
# prepares the rt-folder for the RT simulations
#
##############################################################################
#from __future__ import print_function
from sys import argv
from yambopy     import *
import argparse

print ('This script breaks the symmetries of a given nscf run and')
print ('prepares the rt-folder for the RT simulations')
print ('Gives two arguments')
print ('arg1: folder with nscf data')
print ('arg2: folder for RT simulation')
print ('arg3: prefix')

parser = argparse.ArgumentParser(description='Map of a double-grid')
parser.add_argument('-i' ,'--input'    , help='Folder with nscf data')
parser.add_argument('-o' ,'--output'   , help='Folder for RT simulation')
parser.add_argument('-p' ,'--prefix'    ,help='Prefix')
args = parser.parse_args()

#  print ('No folder given')
print ('Folder of nscf data     ===>>>  ' ,args.input)
print ('Folder of RT simulation ===>>>  ' ,args.output)
print ('Prefix                  ===>>>  ' ,args.prefix)
print ('')

nscf_folder = args.input
rt_folder   = args.output
prefix      = args.prefix
  
# Generation of the database folder

if not os.path.isdir('database'):
  os.system('cd %s/%s.save ; p2y -O ../../database' % (nscf_folder, prefix))
  os.system('cd database; yambo')
  
# Breaking of symmetries

if not os.path.isdir(rt_folder):
  breaking_symmetries([1,0,0], [0,1,0], rt_folder)
