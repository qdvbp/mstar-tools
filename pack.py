'''
	Mstar bin firmware packer
'''

'''
	Header structure
	-------
	Multi-line script which contains MBOOT commands
	The header script ends with line: '% <- this is end of file symbol'
	Line separator is '\n'
	The header is filled by 0xFF to 16KB
	The header size is always 16KB
'''

'''
	Bin structure
	-------
	Basically it's merged parts:
	[part 1]
	[part 2]
	....
	[part n]
	Each part is 4 byte aligned (filled by 0xFF)
'''

'''
	Footer structure
	|MAGIC|CRC1: SWAPPED HEADER CRC32|CRC2: SWAPPED BIN CRC32|FIRST 16 BYTES OF HEADER| - NORMAL
	|MAGIC|CRC1: SWAPPED HEADER CRC32|CRC2: SWAPPED MERGED CRC32|FIRST 16 BYTES OF HEADER| - XGIMI
	|CRC0: SWAPPED BIN CRC32|MAGIC|CRC1: SWAPPED HEADER CRC32|CRC2: SWAPPED MERGED CRC32|FIRST 16 BYTES OF HEADER| - PB803
	# XGIMI uses HEADER+BIN+MAGIC+HEADER_CRC to calculate crc2
	# Software for TP.MS338E.PB803 mainboard uses HEADER+BIN+BIN_CRC+MAGIC+HEADER_CRC to calculate crc2
	# To select use CRC_TYPE = [NORMAL, XGIMI, PB803] in the main config section. By default CRC_TYPE = NORMAL.
'''

import configparser
import sys
import datetime
import os
import struct
import utils
import shutil

today = datetime.datetime.now()
tmpDir = 'tmp'
headerPart = os.path.join(tmpDir, '~header')
binPart = os.path.join(tmpDir, '~bin') 
footerPart = os.path.join(tmpDir, '~footer') 

print ("mstar-bin-tool pack.py v.1.1_sha-man")

# Command line args
if len(sys.argv) == 1: 
	print ("Usage: pack.py <config file>")
	print ("Example: pack.py configs/letv-x355pro.ini")
	quit()

configFile = sys.argv[1]

# Parse config file
config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
#config = configparser.ConfigParser()
config.read(configFile)

# Main
main = config['Main'];
firmwareFileName = main['FirmwareFileName']
projectFolder = main['ProjectFolder']
useHexValuesPrefix = utils.str2bool(main['useHexValuesPrefix'])

SCRIPT_FIRMWARE_FILE_NAME = main['SCRIPT_FIRMWARE_FILE_NAME']
DRAM_BUF_ADDR = main['DRAM_BUF_ADDR']
MAGIC_FOOTER = main['MAGIC_FOOTER']
HEADER_SIZE = utils.sizeInt(main['HEADER_SIZE'])

# XGIMI uses HEADER+BIN+MAGIC+HEADER_CRC to calculate crc2
# TVs with TP.MS338E.PB803 mainboard use HEADER+BIN+BIN_CRC+MAGIC+HEADER_CRC to calculate crc2
XGIMI_CRC = False
PB803_CRC = False
if 'CRC_TYPE' in main:
	if (main['CRC_TYPE'].upper() == 'XGIMI'):
		XGIMI_CRC = True
	if (main['CRC_TYPE'].upper() == 'PB803'):
		XGIMI_CRC = True
		PB803_CRC = True
		
# Header
header = config['HeaderScript'];
if 'Label' in header:
	headerScriptLabel = config.get('HeaderScript', 'Label', raw = True)
else:
	headerScriptLabel = ''
headerScriptPrefix = config.get('HeaderScript', 'Prefix', raw = True)
headerScriptSuffix = config.get('HeaderScript', 'Suffix', raw = True)

# Parts
parts = list(filter(lambda s: s.startswith('part/'), config.sections()))

print("\n")
print ("[i] Date: {:%d/%m/%Y %H:%M:%S}".format(today))
print ("[i] Firmware file name: {}".format(firmwareFileName))
print ("[i] Project folder: {}".format(projectFolder))
print ("[i] Use hex values: {}".format(useHexValuesPrefix))
print ("[i] Script firmware filename: {}".format(SCRIPT_FIRMWARE_FILE_NAME))
print ("[i] DRAM_BUF_ADDR: {}".format(DRAM_BUF_ADDR))
print ("[i] MAGIC_FOOTER: {}".format(MAGIC_FOOTER))
print ("[i] HEADER_SIZE: {}".format(HEADER_SIZE))
print ("[i] XGIMI_CRC: {}".format(XGIMI_CRC))
print ("[i] PB803_CRC: {}".format(PB803_CRC))

# Create working directory
print ('[i] Create working directory ...')
utils.createDirectory(tmpDir)

print ('[i] Generating header and bin ...')
# Initial empty bin to store merged parts
open(binPart, 'w').close()

with open(headerPart, 'wb') as header:
	if headerScriptLabel:
		headerScriptLabel = headerScriptLabel.replace('\\#', '#')
		headerScriptLabel = headerScriptLabel.format(time=today, timestamp=int(today.timestamp()))
		header.write(headerScriptLabel.encode())
		header.write('\n\n'.encode())
	else:
		header.write('#-------------USB Upgrade Bin Info----------------.'.encode())
		header.write('# Device : ironman.'.encode())
		header.write('# Build PATH : /studio2/MSD848_CODE/android.'.encode())
		header.write('# Build TIME : {:%Y-%m-%d %H:%M:%S}\n'.format(today).encode())
		header.write('# Build TIME STAMP : {}..'.format(int(today.timestamp())).encode())

	# Directive tool
	directive = utils.directive(header, DRAM_BUF_ADDR, useHexValuesPrefix)

	header.write('# File Partition: set_partition'.encode())
	header.write(headerScriptPrefix.encode())
	header.write('\n\n'.encode())

#	header.write('# Partitions'.encode())
	for sectionName in parts:

		part = config[sectionName]
		name = sectionName.replace('part/', '')
		create = utils.str2bool(utils.getConfigValue(part, 'create', ''))
		size = utils.getConfigValue(part, 'size', 'NOT_SET')
		erase = utils.str2bool(utils.getConfigValue(part, 'erase', ''))
		type = utils.getConfigValue(part, 'type', 'NOT_SET')
		imageFile = utils.getConfigValue(part, 'imageFile', 'NOT_SET')
		chunkSize = utils.sizeInt(utils.getConfigValue(part, 'chunkSize', '0'))
		lzo = utils.str2bool(utils.getConfigValue(part, 'lzo', ''))
		memoryOffset = utils.getConfigValue(part, 'memoryOffset', 'NOT_SET')
		emptySkip = utils.str2bool(utils.getConfigValue(part, 'emptySkip', 'True'))
		sparse = utils.str2bool(utils.getConfigValue(part, 'sparse', ''))

		print("\n")
		print("[i] Processing partition")
		print("[i]      Name: {}".format(name))
		print("[i]      Create: {}".format(create))
		print("[i]      Size: {}".format(size))
		print("[i]      Erase: {}".format(erase))
		print("[i]      Type: {}".format(type))
		print("[i]      Image: {}".format(imageFile))
		print("[i]      LZO: {}".format(lzo))
		print("[i]      SPARSE: {}".format(sparse))
		print("[i]      Memory Offset: {}".format(memoryOffset))
		print("[i]      Empty Skip: {}".format(emptySkip))
		
		if (lzo & sparse):
			print ('[!] CONFIG ERROR: you cannot use both LZO and SPARSE for one partition')
			quit()

		emptySkip = utils.bool2int(emptySkip) # 0 - False, 1 - True

		if (create):
			directive.create(name, size)

		if (erase and imageFile == 'NOT_SET'):
			directive.erase_p(name)

		if (type == 'partitionImage'):
		
			header.write('\n'.encode())
			header.write('# File Partition: {}\n'.format(name).encode())		
		
			if sparse:
				print ('[i]      Converting img to sparse ...')
				sparseFile = os.path.join(tmpDir, name + '.sparse')
				utils.img_to_sparse(imageFile, sparseFile)
			
				print ('[i]      Splitting sparse file...')
				chunks = utils.sparse_split(sparseFile, tmpDir, chunkSize)
			else:
				if (chunkSize > 0):
					print ('[i]      Splitting ...')
					chunks = utils.splitFile(imageFile, tmpDir, chunksize = chunkSize)
				else:
					# It will contain whole image as a single chunk
					chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)

			for index, inputChunk in enumerate(chunks):
				print ('[i]      Processing chunk: {}'.format(inputChunk))
				(name1, ext1) = os.path.splitext(inputChunk)
				if lzo:
					outputChunk = name1 + '.lzo'
					print ('[i]      LZO: {} -> {}'.format(inputChunk, outputChunk))
					utils.lzo(inputChunk, outputChunk)
				else:
					outputChunk = inputChunk

				# Size, offset (hex)
				size = "{:02X}".format(os.path.getsize(outputChunk))
				offset = "{:02X}".format(os.path.getsize(binPart) + HEADER_SIZE)

				directive.filepartload(SCRIPT_FIRMWARE_FILE_NAME, offset, size)
				if (index == 0 and erase): 
					directive.erase_p(name) 

				print ('[i]      Align chunk')
				utils.alignFile(outputChunk)

				print ('[i]      Append: {} -> {}'.format(outputChunk, binPart))
				utils.appendFile(outputChunk, binPart)

				if lzo:
					if index == 0:
						directive.unlzo(name, size, DRAM_BUF_ADDR, emptySkip)
					else:
						directive.unlzo_cont(name, size, DRAM_BUF_ADDR, emptySkip)
				elif sparse:
					directive.sparse_write (name, DRAM_BUF_ADDR)
				else:
					if len(chunks) == 1:
						directive.write_p(name, size, DRAM_BUF_ADDR, emptySkip)
					else:
						# filepartload 50000000 MstarUpgrade.bin e04000 c800000
						# mmc write.p.continue 50000000 system 0 c800000 1
						# filepartload 50000000 MstarUpgrade.bin d604000 c800000
						# mmc write.p.continue 50000000 system 64000 c800000 1
						# Why offset is 64000 but not c800000 ???
						print ('[!] UNSUPPORTED: mmc write.p.continue')
						quit()

		if (type == 'secureInfo'):

			chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)
			outputChunk = chunks[0]

			size = "{:02X}".format(os.path.getsize(outputChunk))
			offset = "{:02X}".format(os.path.getsize(binPart) + HEADER_SIZE)
			directive.filepartload(SCRIPT_FIRMWARE_FILE_NAME, offset, size)

			print ('[i]      Align')
			utils.alignFile(outputChunk)

			print ('[i]      Append: {} -> {}'.format(outputChunk, binPart))
			utils.appendFile(outputChunk, binPart)
			directive.store_secure_info(name)

		if (type == 'nuttxConfig'):

			chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)
			outputChunk = chunks[0]

			size = "{:02X}".format(os.path.getsize(outputChunk))
			offset = "{:02X}".format(os.path.getsize(binPart) + HEADER_SIZE)
			directive.filepartload(SCRIPT_FIRMWARE_FILE_NAME, offset, size)

			print ('[i]      Align')
			utils.alignFile(outputChunk)

			print ('[i]      Append: {} -> {}'.format(outputChunk, binPart))
			utils.appendFile(outputChunk, binPart)
			directive.store_nuttx_config(name)

		if (type == 'sboot'):
		
			header.write('\n'.encode())
			header.write('# File Partition: {}\n'.format(name).encode())		

			chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)
			outputChunk = chunks[0]

			size = "{:02X}".format(os.path.getsize(outputChunk))
			offset = "{:02X}".format(os.path.getsize(binPart) + HEADER_SIZE)
			directive.filepartload(SCRIPT_FIRMWARE_FILE_NAME, offset, size)

			print ('[i]      Align')
			utils.alignFile(outputChunk)

			print ('[i]      Append: {} -> {}'.format(outputChunk, binPart))
			utils.appendFile(outputChunk, binPart)
			directive.write_boot(size, DRAM_BUF_ADDR, emptySkip)
			
		if (type == 'inMemory'):
		
			chunks = utils.splitFile(imageFile, tmpDir, chunksize = 0)
			outputChunk = chunks[0]
			
			size = "{:02X}".format(os.path.getsize(outputChunk))
			offset = "{:02X}".format(os.path.getsize(binPart) + HEADER_SIZE)
			directive.filepartload(SCRIPT_FIRMWARE_FILE_NAME, offset, size, memoryOffset=memoryOffset)
			
			print ('[i]      Align')
			utils.alignFile(outputChunk)
			
			print ('[i]      Append: {} -> {}'.format(outputChunk, binPart))
			utils.appendFile(outputChunk, binPart)
		
		
			
	header.write('\n'.encode())
	header.write('# File Partition: set_config'.encode())
	header.write(headerScriptSuffix.encode())
	header.write('\n'.encode())

	header.write('% <- this is end of file symbol\n'.encode())
	header.flush()

	print ('[i] Fill header script to 16KB')
	header.write( ('\xff' * (HEADER_SIZE - os.path.getsize(headerPart))).encode(encoding='iso-8859-1') ) 

print ('[i] Generating footer ...')

if (XGIMI_CRC):
	# NB XGIMI uses HEADER+BIN+MAGIC+HEADER_CRC to calculate crc2
	headerCRC = utils.crc32(headerPart)
	header16bytes = utils.loadPart(headerPart, 0, 16)
	binCRC = utils.crc32(binPart)

	# Step #1. Merge HEADER+BIN+MAGIC+HEADER_CRC to one file
	mergedPart = os.path.join(tmpDir, '~merged')
	open(mergedPart, 'w').close()
	utils.appendFile(headerPart, mergedPart)
	utils.appendFile(binPart, mergedPart)
	with open(mergedPart, 'ab') as part:
		# If PB803 CRC type selected then adding BIN_CRC to the merged file	
		if (PB803_CRC):
			print ('[i]      Bin CRC   : 0x{:02X}'.format(binCRC))
			part.write(struct.pack('L', binCRC))
		print ('[i]      Magic     : {}'.format(MAGIC_FOOTER))
		part.write(MAGIC_FOOTER.encode())
		print ('[i]      Header CRC: 0x{:02X}'.format(headerCRC))
		part.write(struct.pack('L', headerCRC))
	
	# Step #2 Calculate CRC2
	mergedCRC = utils.crc32(mergedPart)
	with open(footerPart, 'wb') as footer:
		print ('[i]      Merged CRC: 0x{:02X}'.format(mergedCRC))
		footer.write(struct.pack('L', mergedCRC))
		print ('[i]      First 16 bytes of header: {}'.format(header16bytes))
		footer.write(header16bytes)

	print ('[i] Merging parts ...')
	open(firmwareFileName, 'w').close()
	utils.appendFile(mergedPart, firmwareFileName)
	utils.appendFile(footerPart, firmwareFileName)
else:
	headerCRC = utils.crc32(headerPart)
	binCRC = utils.crc32(binPart)
	header16bytes = utils.loadPart(headerPart, 0, 16)
	with open(footerPart, 'wb') as footer:
		print ('[i]      Magic: {}'.format(MAGIC_FOOTER))
		footer.write(MAGIC_FOOTER.encode())
		print ('[i]      Header CRC: 0x{:02X}'.format(headerCRC))
		footer.write(struct.pack('L', headerCRC)) # struct.pack('L', data) <- returns byte swapped data
		print ('[i]      Bin CRC: 0x{:02X}'.format(binCRC))
		footer.write(struct.pack('L', binCRC))
		print ('[i]      First 16 bytes of header: {}'.format(header16bytes))
		footer.write(header16bytes)

	print ('[i] Merging header, bin, footer ...')
	open(firmwareFileName, 'w').close()
	utils.appendFile(headerPart, firmwareFileName)
	utils.appendFile(binPart, firmwareFileName)
	utils.appendFile(footerPart, firmwareFileName)

shutil.rmtree(tmpDir)
print ('[i] Done.')
