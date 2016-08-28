#!/usr/bin/env python

"""
Module for the Sentinel Daemon
"""

### TODO Items as of 2016-08-26 ###
#
#  - Implement proposal checks against available budget
#    (Requires new dashd rpc function)
#
#  - Acquire superblock cycle information from dashd
#    (Requires new dashd rpc function)
#
#  - Limit superblock payments to total available budget
#
#  - Set PROPOSAL_QUORUM correctly
#
#  - Check if there's a better way to handle amounts than
#    using floats (we should probably handle these like
#    dashd does)
#
#  - Implement cleanup of old/expired DB objects
#
#  - Check rpc submit call for permanent failures and log
#    error message in event table
#
#  - Implement a sentineld debug log
#
#  - Implement top level restart on exception
#
#  - Check comments for any TODO's not listed here
#
#  - Review implementation against spec document
#    to ensure all functionality defined in the spec
#    has been implemented
#
#  - Other simplifications, refactorings and/or improvements ?
#
### End TODO ###

import sys
import os

sys.path.append( "lib" )
sys.path.append( "scripts" ) 

dir_path = os.path.dirname( os.path.realpath(__file__) )

sys.path.append( os.path.abspath( os.path.join( dir_path, ".." ) ) )

import cmd
import misc
import libmysql
import config
import crontab
import cmd, sys
import govtypes
import random 
import json 
import time
import datetime
import binascii
import calendar
import hashlib
import re

import base58_dash as base58

#from governance import Event
#from classes import Proposal, Superblock
from dashd import CTransaction, rpc_command

import time

# Global variable set by SentinelDaemon
TESTNET = False

# Controls debugging messages generated by printd
DEBUG = True

GOVERNANCE_UPDATE_PERIOD_SECONDS = 30

# Number of blocks before a superblock to create superblock objects for
# auto vote.
#SUPERBLOCK_CREATION_DELTA = 10
SUPERBLOCK_CREATION_DELTA = 1

# Minimum number of absolute yes votes to include a proposal in a superblock
#PROPOSAL_QUORUM = 10
# TODO: Should be calculated based on the number of masternodes
# with an absolute minimum of 10 (maybe 1 for testnet)
# ie. max( 10, (masternode count)/10 ) 
PROPOSAL_QUORUM = 0

# For testing, set to True in production
ENABLE_PROPOSAL_VALIDATION = True

# For testing, set to True in production
ENABLE_SUPERBLOCK_VALIDATION = True

# For testing, set to False in production
ENABLE_WIN_ALL_ELECTIONS = True

OBJECT_TYPE_MAP = { govtypes.trigger: "trigger", govtypes.proposal: "proposal" }
OBJECT_TYPE_REVERSE_MAP = { "trigger": govtypes.trigger, "proposal": govtypes.proposal }

DB = libmysql.connect( config.hostname, config.username, config.password, config.database )

BASE58_CHARSET = frozenset( [ c for c in base58.b58chars ] )

def printd( *args ):
    if DEBUG:
        argstring = " ".join( [ str( arg ) for arg in args ] )
        print( argstring )

def validateDashAddress( address ):
    # Only public key addresses are allowed 
    # A valid address is a RIPEMD-160 hash which contains 20 bytes
    # Prior to base58 encoding 1 version byte is prepended and
    # 4 checksum bytes are appended so the total number of
    # base58 encoded bytes should be 25.  This means the number of characters
    # in the encoding should be about 34 ( 25 * log2( 256 ) / log2( 58 ) ).
    validVersion = 76 if not TESTNET else 140
    print "validateDashAddress: address = ", address

    # Check length (This is important because the base58 librray has problems
    # with long addresses (which are invalid anyway).
    if ( ( len( address ) < 34 ) or ( len( address ) > 35 ) ):
        return False

    # Check that characters are valid, otherwise base58 library
    # will probably throw an exception.
    # Would using a compiled regex be faster than this ?
    for c in address:
        if c not in BASE58_CHARSET:
            return False

    version = base58.get_bcaddress_version( address )
    if version is None:
        return False
    return ( version == validVersion )

def computeHashValue( data ):
    m = hashlib.sha256()
    m.update( data )
    hex = m.hexdigest()
    return int( hex, 16 )

def isTestnet():
    result = rpc_command( "getinfo" )
    lines = result.splitlines()
    for line in lines:
        m = re.match( r'^.*testnet.*:\s*(\S+)\s*,\s*$', line )
        if m is not None:
            value = m.group( 1 ).lower()
            if value == "true":
                return True
            else:
                return False
    return None

def getGovernanceObjects():
    result = rpc_command( "gobject list" )
    #print "result = ", result
    govobjs = json.loads( result )
    return govobjs

def getMasternodes():
    result = rpc_command( "masternodelist full" )
    #print "result = ", result
    rec = json.loads( result )
    #print "rec = ", rec
    return rec

def getMyVin():
    result = rpc_command( "masternode status" )
    rec = json.loads( result )
    #print "rec = ", rec
    if 'vin' not in rec:
        return None
    vinstr = rec['vin']
    #print "vinstr = ", vinstr
    m = re.match( r'^\s*CTxIn\(COutPoint\(\s*([0-9a-fA-F]+)\s*,\s*(\d+)\s*\).*$', vinstr )
    if m is None:
        print "No match"
        return None
    vin = m.group( 1 ) + "-" + m.group( 2 )
    return vin.strip()

def getBlockCount():
    result = rpc_command( "getblockcount" )
    return int( result )

def getSuperblockCycle():
    # TODO: Add dashd rpc call for this
    # For now return the testnet value
    #return 24
    return 5

def getSuperblockBudgetAllocation():
    # TODO: Add dashd rpc call for this
    # For now return an arbitrary value for testing
    return 1000

def getCurrentBlockHash():
    height = getBlockCount()
    result = rpc_command( "getblockhash %d" % ( height ) )
    return result

def createGovernanceObject( objRec ):
    dstr = objRec['DataString']
    subtype = dstr[0]
    gobj = GovernanceObject()
    
    if subtype == 'trigger':
        pass
    elif subtype == 'proposal':
        pass
    else:
        raise( Exception( "createGovernanceObject: ERROR: Unknown subtype: %s" % ( subtype ) ) )

class DBObject:

    def __init__( self ):
        pass
        self.id = None

    def makeFields( self, cls ):
        columns = cls.getColumns()
        for cname in columns:
            self.__dict__[cname] = None

    @staticmethod
    def getTableName():
        return "default"

    @staticmethod
    def getColumns():
        columns = []
        return columns

    @classmethod
    def getColumnSet( cls ):
        return frozenset( cls.getColumns() )

    @staticmethod
    def getIdColumn():
        return ''

    @classmethod
    def getSelectList( cls ):
        selectList = ""
        columns = cls.getColumns()
        for i in range( len( cls.getColumns() ) ):
            cname = columns[i]
            selectList += cname
            if i < ( len( columns ) - 1 ):
                selectList += ", "
        return selectList

    @classmethod
    def getSelectSQL( cls ):
        sql = "select " + cls.getSelectList()
        sql += " from " + cls.getTableName() + " "
        return sql

    @classmethod
    def getInsertSQL( cls ):
        sql = "insert into %s ( " % ( cls.getTableName() )
        columns = cls.getColumns()
        for i in range( 1, len( columns ) ):
            cname = columns[i]
            sql += cname
            if i < ( len( columns ) - 1 ):
                sql += ", "
        sql += " ) values( "
        for i in range( 1, len( columns ) ):
            sql += "%s"
            if i < ( len( columns ) - 1 ):
                sql += ", "
        sql += " )"
        return sql

    @classmethod
    def getUpdateSQL( cls ):
        columns = cls.getColumns()
        sql = "update %s set " % ( cls.getTableName() )
        for i in range( 1, len( columns ) ):
            cname = columns[i]
            sql += cname + " = %s"
            if i < ( len( columns ) - 1 ):
                sql += ", "
        sql += " where %s " % ( cls.getIdColumn() ) 
        sql += " = %s"
        return sql

    def isNew( self ):
        print "isNew: self.id = ", self.id
        return ( self.id is None )

    def getObjectId( self, cls ):
        idColumn = cls.getIdColumn()
        objectId = self.__dict__.get( idColumn )
        return objectId

    def setObjectId( self, objectId ):
        """Sets both the id for the base governance class and for the subclass"""
        idColumn = self.getIdColumn()
        setattr( self, idColumn, objectId )
        self.id = objectId
        
    def initObjectId( self, objectId ):
        """Sets the id for the subclass only if not already set"""
        idColumn = self.getIdColumn()
        currentObjectId = getattr( self, idColumn, None )
        if ( ( currentObjectId is not None ) and
             ( self.id is not None ) ):
            return
        setattr( self, idColumn, objectId )

    def getMemberSQL( self, cls, name ):
        if name not in cls.getColumns():
            raise Exception( "DBObject.getMemberSQL: ERROR Unknown field name: %s" % ( name ) )
        value = self.__dict__[name]
        #if value is None:
        #    return "NULL"
        return value

    def getInstanceData( self, cls ):
        data = []
        columns = cls.getColumns()
        #print "getIntanceData: cls = %s, class = %s, columns = %s" % ( cls, self.__class__, columns )
        #print "dir(self) = ", dir( self )
        for cname in columns[1:]:
            data.append( self.getMemberSQL( cls, cname ) )
        return data

    def store( self ):
        # Overridden in subclasses
        return None

    def load( self ):
        # Overridden in subclasses
        return None

    def storeInternal( self, cls ):
        data = self.getInstanceData( cls )
        objectId = self.getObjectId( cls )
        if self.isNew():
            sql = cls.getInsertSQL()
        else:
            sql = cls.getUpdateSQL()
            data.append( objectId )
        c = libmysql.db.cursor()
        printd( "DBObject.storeInternal: sql = ", sql )
        printd( "DBObject.storeInternal: data = ", data )
        c.execute( sql, data )
        insertId = libmysql.db.insert_id()
        c.close()
        libmysql.db.commit()
        return insertId

    def loadInternal( self, cls ):
        objectId = self.getObjectId( cls )
        printd( "DBObject.loadInternal: cls = %s, objectId = %s" % ( cls, objectId ) )
        if objectId is None:
            raise( Exception( "DBObject.loadInternal: ERROR id is NULL" ) )
        sql = cls.getSelectSQL()
        sql += "where %s" % ( cls.getIdColumn() )
        sql += " = %s"
        printd( "DBObject.loadInternal: sql = ", sql )
        c = libmysql.db.cursor()
        c.execute( sql, ( objectId ) )
        row = c.fetchone()
        if row is None:
            raise( Exception( "DBObject.loadInternal: ERROR row not found for id = %s" % ( objectId ) ) )
        columns = cls.getColumns()
        if len( row ) != len( columns ):
            raise( Exception( "DBObject.loadInternal: ERROR incorrect row length" ) )
        for i in range( 1, len( columns ) ):
            setattr( self, columns[i], row[i] )

class GovernanceObject(DBObject):

    def __init__( self, name ):
        self.makeFields( GovernanceObject )
        self.object_name = name
        self.object_revision = govtypes.FIRST_REVISION
        self.subtype = None
        self.parent_id = 0
        self.object_creation_time = calendar.timegm( time.gmtime() )
        self.object_hash = 0
        self.object_parent_hash = 0
        self.object_type = 0
        self.object_fee_tx = ''
        self.object_data = binascii.hexlify(json.dumps([]))
        self.absolute_yes_count = 0
        self.yes_count = 0
        self.no_count = 0
        self.object_status = 'UNKNOWN'
        self.object_origin = 'UNKNOWN'
        self.is_valid = None

    @staticmethod
    def getObjectType( object_id ):
        sql = "select object_type from governance_object where id = %s"
        c = libmysql.db.cursor()
        c.execute( sql, ( object_id ) )
        row = c.fetchone()
        c.close()
        if row is None:
            return None
        return row[0]

    @staticmethod
    def getTableName():
        return "governance_object"

    @staticmethod
    def getColumns():
        columns = [ 'id', 
                    'parent_id',
                    'object_creation_time',
                    'object_hash',
                    'object_parent_hash',
                    'object_name',
                    'object_type',
                    'object_revision',
                    'object_data',
                    'object_fee_tx',
                    'absolute_yes_count',
                    'yes_count',
                    'no_count',
                    'object_status',
                    'object_origin',
                    'is_valid' ]
        return columns

    @classmethod
    def getColumnSet( cls ):
        return frozenset( self.getColumns() )

    @staticmethod
    def getLocalColumns():
        # local columns are excluded from the JSON and object hash
        localColumns = frozenset( [ 'id',
                                    'parent_id',
                                    'object_name',
                                    'absolute_yes_count',
                                    'yes_count',
                                    'no_count',
                                    'object_status',
                                    'object_origin',
                                    'is_valid' ] )
        return localColumns

    @staticmethod
    def getIdColumn():
        return 'id'

    def loadJSON( self, rec ):
        self.object_data = rec['DataHex']
        self.object_hash = rec['Hash']
        self.object_fee_tx = rec['CollateralHash']
        self.absolute_yes_count = int( rec['AbsoluteYesCount'] )
        self.yes_count = int( rec['YesCount'] )
        self.no_count = int( rec['NoCount'] )
        self.loadJSONFields( rec )

    def getJSON( self ):
        obj = self.getJSONFields()
        objpair = [( OBJECT_TYPE_MAP[self.subtype], obj )]
        jsonData = json.dumps( objpair, sort_keys = True )
        printd( "getJSON: jsonData = ", jsonData )
        return jsonData

    def getJSONHex( self ):
        hexdata = binascii.hexlify( self.getJSON() )
        return hexdata
        
    def updateObjectData( self ):
        self.object_data = self.getJSONHex()

    def loadJSONFields( self, rec ):
        objpair = json.loads( binascii.unhexlify( rec['DataHex'] ) )[0]
        objrec = objpair[1]
        columns = self.getColumns()
        localColumns = self.getLocalColumns()
        for cname in columns:
            if cname in localColumns:
                continue
            value = objrec[cname]
            setattr( self, cname, value )

    def getJSONFields( self ):
        obj = {}
        # Used by dashd to determine object type
        obj['type'] = self.subtype
        columns = self.getColumns()
        localColumns = self.getLocalColumns()
        for cname in columns:
            if cname in localColumns:
                continue
            obj[cname] = getattr( self, cname )
        return obj

    def existsInDb( self ):
        if len( self.object_hash ) < 1:
            return False
        sql = GovernanceObject.getSelectSQL() + " where object_hash = %s and object_origin = 'REMOTE' "
        #print "existsInDb: sql = ", sql
        c = libmysql.db.cursor()
        c.execute( sql, ( self.object_hash ) )
        result = c.fetchone()
        c.close()
        if result is None:
            self.setObjectId( None )
            return False
        else:
            self.setObjectId( result[0] )
            return True

    def isValid( self ):
        # Base class objects aren't valid
        return False
    
class Superblock(GovernanceObject):

    def __init__( self, name ):
        GovernanceObject.__init__( self, name )
        self.makeFields( Superblock )
        self.object_type = govtypes.trigger
        self.subtype = govtypes.trigger
        self.tableName = "superblock"
        self.superblock_name = name
        self.object_name = name
        self.event_block_height = 0
        self.payment_addresses = ''
        self.payment_amounts = ''

    @staticmethod
    def getTableName():
        return "superblock"

    @staticmethod
    def getColumns():
        columns = [ 'id',
                    'governance_object_id',
                    'superblock_name',
                    'event_block_height',
                    'payment_addresses',
                    'payment_amounts' ]
        return columns

    @staticmethod
    def getLocalColumns():
        # Note: superblock_name is excluded from the JSON and object hash
        # because it is randomly generated and isn't essential
        # to superblock identity
        localColumns = frozenset( [ 'id',
                                    'governance_object_id',
                                    'superblock_name' ] )
        return localColumns

    @staticmethod
    def getIdColumn():
        return 'governance_object_id'

    def store( self ):
        insertId = self.storeInternal( GovernanceObject )
        self.initObjectId( insertId )
        self.storeInternal( Superblock )
        self.id = insertId
        return self.id

    def load( self ):
        self.loadInternal( GovernanceObject )
        self.loadInternal( Superblock )
        self.setObjectId( self.id )

    def isValid( self ):
        printd( "Superblock.isValid name = ", self.superblock_name )
        if not ENABLE_SUPERBLOCK_VALIDATION:
            printd( "Superblock.isValid Validation disabled, returning True" )
            return True
        sql = "select governance_object_id, object_status from superblock, governance_object where "
        sql += "superblock.governance_object_id = governance_object.id and "
        sql += "event_block_height = %s and "
        sql += "object_origin = 'LOCAL' "
        c = libmysql.db.cursor()
        c.execute( sql, self.event_block_height )
        rows = c.fetchall()
        if len( rows ) == 0:
            # If we have no local superblock for this event_block_height
            # we make no decision on validity (implies no vote).
            printd( "Superblock.isValid No local match, returning None" )
            return None
        if len( rows ) != 1:
            # Something's wrong if this query returns more than 1 row so return False
            printd( "Superblock.isValid Too many matching rows, returning False" )
            return False
        row = rows[0]
        localSuperblock = GFACTORY.createFromTable( 'trigger', row[0] )
        if localSuperblock.event_block_height != self.event_block_height:
            printd( "Superblock.isValid Invalid superblock: event_block_heignt doesn't match, returning False" )
            return False
        if localSuperblock.payment_addresses != self.payment_addresses:
            printd( "Superblock.isValid Invalid superblock: payment_addresses don't match, returning False" )
            return False
        if localSuperblock.payment_amounts != self.payment_amounts:
            printd( "Superblock.isValid Invalid superblock: payment_amounts don't match, returning False" )
            return False
        printd( "Superblock.isValid returning True" )
        return True

class Proposal(GovernanceObject):

    def __init__( self, name ):
        GovernanceObject.__init__( self, name )
        self.makeFields( Proposal )
        self.object_type = govtypes.proposal
        self.subtype = govtypes.proposal
        self.tableName = "proposal"
        self.proposal_name = name
        self.object_name = name
        self.start_epoch = 0
        self.end_epoch = 0
        self.payment_address = ''
        self.payment_amount = 0

    @staticmethod
    def getTableName():
        return "proposal"

    @staticmethod
    def getColumns():
        columns = [ 'id',
                    'governance_object_id',
                    'proposal_name',
                    'start_epoch',
                    'end_epoch',
                    'payment_address',
                    'payment_amount' ]
        return columns

    @staticmethod
    def getLocalColumns():
        # Note: proposal_name is included in JSON and object hash
        # because it is set manually and is essential to a proposal's
        # identity.
        localColumns = frozenset( [ 'id',
                                    'governance_object_id' ] )
        return localColumns

    @staticmethod
    def getIdColumn():
        return 'governance_object_id'

    def store( self ):
        insertId = self.storeInternal( GovernanceObject )
        self.initObjectId( insertId )
        self.storeInternal( Proposal )
        self.id = insertId
        return self.id

    def load( self ):
        self.loadInternal( GovernanceObject )
        self.loadInternal( Proposal )
        self.setObjectId( self.id )

    def isValid( self ):
        if not ENABLE_PROPOSAL_VALIDATION:
            return True
        # Check name
        if not re.match( r'^[-_a-zA-Z0-9]+$', self.proposal_name ):
            printd( "Proposal.isValid Invalid proposal name format: proposal_name = ", self.proposal_name )
            return False
        now = calendar.timegm( time.gmtime() )
        if self.end_epoch <= now:
            printd( "Proposal.isValid Invalid end_epoch(%s) <= now(%s) " % ( self.end_epoch, now ) )
            return False
        if self.end_epoch <= self.start_epoch:
            printd( "Proposal.isValid Invalid end_epoch(%s) <= start_epoch(%s) " % ( self.end_epoch, self.start_epoch ) )
            return False
        if not validateDashAddress( self.payment_address ):
            printd( "Proposal.isValid Invalid payment address: %s" % ( self.payment_address ) )
            return False

        # TODO: Should we be using floats here or treat decimals properly
        try:
            amountValue = float( self.payment_amount )
        except:
            printd( "Proposal.isValid Failed to parse amount: %s" % ( self.payment_amount ) )
            return False

        if amountValue > getSuperblockBudgetAllocation():
            return False

        return True

class Event(DBObject):

    def __init__( self, govobjId = 0 ):
        self.makeFields( Event )
        self.governance_object_id = govobjId
        self.start_time = 0
        self.prepare_time = 0
        self.submit_time = 0
        self.error_time = 0
        self.error_message = ''

    @staticmethod
    def getTableName():
        return "event"

    @staticmethod
    def getColumns():
        columns = [ 'id', 
                    'governance_object_id',
                    'start_time',
                    'prepare_time',
                    'submit_time',
                    'error_time',
                    'error_message' ]
        return columns

    @staticmethod
    def getIdColumn():
        return 'id'

    def load( self ):
        self.loadInternal( Event )

    def store( self ):
        return self.storeInternal( Event )

class GovernanceFactory:

    def __init__( self ):
        pass

    def create( self, subtype, name ):
        govobj = None
        if not isinstance( subtype, basestring ):
            subtype = OBJECT_TYPE_MAP[subtype]
        if subtype == 'trigger':
            govobj = Superblock( name )
        elif subtype == 'proposal':
            govobj = Proposal( name )
        else:
            raise( Exception( "GovernanceFactory.create: ERROR Unknown subtype: %s" % ( subtype ) ) )
        return govobj

    def createFromTable( self, subtype, objectId ):
        printd( "GovernanceFactory.createFromTable Start subtype = %s, objectId = %s" % ( subtype, objectId ) )
        govobj = self.create( subtype, None )
        govobj.setObjectId( objectId )
        printd( "GovernanceFactory.createFromTable Before load, govobj = " % govobj.__dict__ )
        assert( govobj.id == objectId )
        govobj.load()
        printd( "GovernanceFactory.createFromTable After load, govobj = " % govobj.__dict__ )
        assert( govobj.id == objectId )
        return govobj

    def createById( self, objectId ):
        printd( "GovernanceFactory.createById: objectId = ", objectId )
        subtype = GovernanceObject.getObjectType( objectId )
        if subtype is None:
            return None
        govobj = self.createFromTable( subtype, objectId )
        return govobj

GFACTORY = GovernanceFactory()

class SentinelDaemon:

    def __init__( self ):
        global TESTNET
        self.nMainPeriodSeconds = 5
        self.tasks = []
        if isTestnet():
            TESTNET = True
        else:
            TESTNET = False
    
    def addTask( self, task ):
        self.tasks.append( task )

    def runTasks( self ):
        printd( "SentinelDaemon.runTasks: Running tasks" )
        for task in self.tasks:
            if task.isReady():
                task.run()

    def run( self ):
        while True:
            self.runTasks()
            time.sleep( self.nMainPeriodSeconds )


class SentinelTask:

    def __init__( self, nPeriodSeconds = 0 ):
        self.nPeriodSeconds = nPeriodSeconds
        self.nLastRun = 0
    
    def isReady( self ):
        nCurrentTime = time.time()
        if nCurrentTime - self.nLastRun >= self.nPeriodSeconds:
            return True
        return False

    def run( self ):
        pass

class SentinelTaskList(SentinelTask):

    """Represents a list of tasks tha should be run sequentially in order"""

    def __init__( self, nPeriodSeconds ):
        SentinelTask.__init__( self, nPeriodSeconds )
        self.taskList = []
    
    def addTask( self, task ):
        self.taskList.append( task )

    def run( self ):
        for task in self.taskList:
            task.run()
    
class UpdateGovernanceTask(SentinelTask):

    def __init__( self ):
        SentinelTask.__init__( self, GOVERNANCE_UPDATE_PERIOD_SECONDS )

    def run( self ):
        govobjs = getGovernanceObjects()
        newobjs = []
        for key, rec in govobjs.items():
            #print "rec = ", rec
            #print "DataString:", rec['DataString']
            datarec = json.loads( rec['DataString'] )[0]
            subtype = datarec[0]
            name = rec['Name']
            govobj = GFACTORY.create( subtype, name )
            govobj.loadJSON( rec )
            if not govobj.existsInDb():
                newobjs.append( govobj )
        printd( "UpdateGovernanceTask.run len( newobjs ) = ", len( newobjs ) )
        for obj in newobjs:
            valid = obj.isValid()
            obj.is_valid = valid
            obj.object_status = "NEW"
            obj.object_origin = "REMOTE"
            obj.store()

class CreateSuperblockTask(SentinelTask):

    def __init__( self ):
        SentinelTask.__init__( self )
        self.event_block_height = 0
        self.superblock = None

    def run( self ):
        printd( "CreateSuperblockTask.run START" )
        self.superblock = None
        height = getBlockCount()
        cycle = getSuperblockCycle()
        diff = height % cycle
        self.event_block_height = height + diff
        printd( "CreateSuperblockTask: height = %d, cycle = %d, diff = %d" % ( height, cycle, diff ) )
        if ( cycle - diff ) != SUPERBLOCK_CREATION_DELTA:
            return
        # Check if we've already created this superblock
        if self.superblockCreated():
            printd( "CreateSuperblockTask.run Superblock already created, returning" )
            return
        proposals = self.getNewProposalsRanked()
        if len( proposals ) < 1:
            # Don't create empty superblocks
            printd( "CreateSuperblockTask.run No new proposals, returning" )
            return
        printd( "CreateSuperblockTask.run Creating superblock" )
        self.createSuperblock( proposals )
        if self.isElected():
            printd( "CreateSuperblockTask.run Submitting superblock" )
            self.submitSuperblock()

    def isElected( self ):
        """Determine if we are the winner of the current superblock creator election"""
        blockHashVal = computeHashValue( getCurrentBlockHash() )
        myvin = getMyVin()
        if myvin is None:
            # If we're not a master we can't be elected
            printd( "isElected: We're not a masternode, returning False" )
            return False
        masternodes = getMasternodes()
        candidates = []
        for vin, mnstring in masternodes.items():
            fields = filter( lambda x: x != '', [ f.strip() for f in re.split( r'\s+', mnstring ) ] )
            if fields[0] != 'ENABLED':
                continue
            mnHashVal = computeHashValue( vin )
            diff = abs( mnHashVal - blockHashVal )
            crec = { 'vin': vin, 'value': diff }
            candidates.append( crec )
        candidates.sort( key = lambda x: x['value'] )
            
        if len( candidates ) < 1:
            printd( "isElected: No candidates, returning False" )
            return False

        electedVin = candidates[0]['vin']

        printd( "isElected: electedVin = ", electedVin )

        if electedVin == myvin:
            printd( "isElected: We're elected, returning True" )
            return True

        if ENABLE_WIN_ALL_ELECTIONS:
            printd( "isElected: We're not elected, but returning True for testing" )
            return True

        printd( "isElected: We're not elected, returning False" )
        return False

    def submitSuperblock( self ):
        """Submit the superblock we created to the network"""
        if self.superblock is None:
            return
        # We just need to submit the event.  The ProcessEvents task
        # will do the rest of the work.
        event = Event( self.superblock.id )
        event.start_time = misc.get_epoch()
        event.store()
        printd( "CreateSuperblockTask.submitSuperblock Submitted event: ", str( event.__dict__ ) )
        self.superblock.object_status = "SUBMITTED"
        printd( "CreateSuperblockTask.submitSuperblock: Calling store, id = ", self.superblock.id )
        self.superblock.store()
        self.superblock = None
        
    def superblockCreated( self ):
        sql = "select object_status, event_block_height from governance_object, superblock where "
        sql += "governance_object.id = superblock.governance_object_id and "
        sql += "event_block_height = %s and "
        sql += "object_origin = 'LOCAL' "
        c = libmysql.db.cursor()
        c.execute( sql, self.event_block_height )
        rows = c.fetchall()
        if len( rows ) > 0:
            return True
        return False

    def getNewProposalsRanked( self ):
        govTable = GovernanceObject.getTableName()
        propTable = Proposal.getTableName()
        sql = "select "
        sql += "%(propTable)s.governance_object_id " % { 'propTable': propTable }
        sql += "from %s, %s " % ( propTable, govTable )
        sql += "where %s.id = %s.governance_object_id and " % ( govTable, propTable )
        sql += "object_status = 'NEW' and object_origin = 'REMOTE' and is_valid = 1 and "
        sql += "%s.absolute_yes_count >= %s " % ( govTable, PROPOSAL_QUORUM )
        sql += "ORDER BY %s.absolute_yes_count " % ( govTable )
        c = libmysql.db.cursor()
        c.execute( sql )
        rows = c.fetchall()
        proposals = []
        for row in rows:
            proposal = GFACTORY.createFromTable( 'proposal', row[0] )
            proposals.append( proposal )
        return proposals

    def createSuperblock( self, proposals ):
        printd( "createSuperblock: Start, len( proposals ) = ", len( proposals ) )
        payments = []
        allocated = 0.0
        budget = getSuperblockBudgetAllocation()
        for proposal in proposals:
            # TODO: Note: unparseable amounts should have been rejected
            #       as invalid, but should we be using floats here
            #       (see previous comments).
            amountValue = float( proposal.payment_amount )
            allocated += amountValue
            if allocated > budget:
                break
            payment = { 'address': proposal.payment_address,
                        'amount': proposal.payment_amount }
            payments.append( payment )
        sbname = "sb" + str( random.randint(1000000, 9999999) )
        superblock = GFACTORY.create( 'trigger', sbname )
        payment_addresses = ""
        payment_amounts = ""
        for i in range( len( payments ) ):
            payment = payments[i]
            payment_addresses += payment['address']
            payment_amounts += str( payment['amount'] )
            if i < ( len( payments ) - 1 ):
                payment_addresses += "|"
                payment_amounts += "|"
        printd( "createSuperblock: payment_addresses = ", payment_addresses )
        printd( "createSuperblock: payment_amounts = ", payment_amounts )
        superblock.payment_addresses = payment_addresses
        superblock.payment_amounts = payment_amounts
        superblock.object_status = "NEW"
        superblock.object_origin = "LOCAL"
        superblock.is_valid = 1
        superblock.event_block_height = self.event_block_height
        superblock.updateObjectData()
        superblock.store()
        self.superblock = superblock
        printd( "createSuperblock: End, self.superblock.id = ", self.superblock.id )

class AutoVoteTask(SentinelTask):

    def __init__( self ):
        SentinelTask.__init__( self )

    def run( self ):
        self.voteValidSuperblocks()
        self.voteInvalidObjects()

    def voteValidSuperblocks( self ):
        superblocks = self.getValidSuperblocks()
        for superblock in superblocks:
            self.vote( superblock, 'funding', 'yes' )

    def voteInvalidObjects( self ):
        invalidObjects = self.getInvalidObjects()
        for obj in invalidObjects:
            self.vote( obj, 'valid', 'no' )

    def vote( self, govObj, signal, outcome ):
        objHash = govObj.object_hash
        if not misc.is_hash( objHash ):
            raise( Exception( "AutoVoteTask.vote ERROR: Missing object hash for object: %s" % ( govObj.__dict__ ) ) )
        command = "gobject vote-conf %s %s %s" % ( objHash, signal, outcome )
        printd( "vote: command = ", command )
        rpc_command( command )
        govObj.object_status = 'VOTED'
        govObj.store()            
        
    def getInvalidObjects( self ):
        sql = "select id from governance_object where is_valid = 0 and object_origin = 'REMOTE' and object_status = 'NEW' "
        c = libmysql.db.cursor()
        c.execute( sql )
        rows = c.fetchall()
        invalidObjects = []
        for row in rows:
            govobj = GFACTORY.createById( row[0] )
            invalidObjects.append( govobj )
        return invalidObjects

    def getValidSuperblocks( self ):
        sql = "select id from governance_object where object_type = %s and "
        sql += "is_valid = 1 and object_origin = 'REMOTE' and object_status = 'NEW' "
        c = libmysql.db.cursor()
        c.execute( sql, govtypes.trigger )
        rows = c.fetchall()
        superblocks = []
        for row in rows:
            govobj = GFACTORY.createById( row[0] )
            superblocks.append( govobj )
        return superblocks

class ProcessEventsTask(SentinelTask):

    def __init__( self ):
        SentinelTask.__init__( self )

    def getEvents( self, prepared ):
        sql = "select id from event where start_time < NOW() and error_time = 0 and submit_time = 0 "
        if prepared:
            sql += " and prepare_time > 0"
        else:
            sql += " and prepare_time = 0"
        c = libmysql.db.cursor()
        c.execute( sql )
        rows = c.fetchall()
        events = []
        for row in rows:
            event = Event()
            event.setObjectId( row[0] )
            event.load()
            events.append( event )
        return events
        
    def doPrepare( self, event ):
        printd( "doPrepare: event = ", event.__dict__ )
        govobj = GFACTORY.createById( event.governance_object_id )
        printd( "doPrepare: govobj = ", govobj.__dict__ )
        cmd = "gobject prepare %(object_parent_hash)s %(object_revision)s %(object_creation_time)s %(object_name)s %(object_data)s" % govobj.__dict__

        printd( "doPrepare: cmd = ", cmd )

        result = rpc_command( cmd )

        printd( "doPrepare: result = ", result )

        if misc.is_hash( result ):
            hashtx = misc.clean_hash( result )
            printd( " -- got hash:", hashtx )
            govobj.object_fee_tx = hashtx
            printd( "doPrepare: Calling govobj.store, govobj =  ", govobj.__dict__ )
            govobj.store()
            event.prepare_time = misc.get_epoch()
            event.store()
        else:
            printd( " -- got error:", result )
            event.error_time = misc.get_epoch()
            # separately update event error message
            event.error_message = result
            event.store()

    def doSubmit( self, event ):
        govobj = GFACTORY.createById( event.governance_object_id )
        cmd = "gobject submit %(object_fee_tx)s %(object_parent_hash)s %(object_revision)s %(object_creation_time)s %(object_name)s %(object_data)s" % govobj.__dict__

        printd( "doSubmit: cmd = ", cmd )

        if not misc.is_hash( govobj.object_fee_tx ):
            printd( "doSubmit: Warning no object_fee_tx hash" )
            return

        result = rpc_command( cmd )

        printd( "doSubmit: result = ", result )

        if misc.is_hash( result ):
            event.submit_time = misc.get_epoch()
            event.store()
            govobj.object_hash = result
            govobj.store()
        # If the submit call did not succeed assume more confirmations needed
        # so we will try again later.
        # TODO: Check for other errors here and set the error fields

    def run( self ):
        printd( "ProcessEventsTask.run START" )
        toPrepare = self.getEvents( False )
        printd( "ProcessEventsTask.run Number events to prepare = ", len( toPrepare ) )
        for event in toPrepare:
            self.doPrepare( event )

        toSubmit = self.getEvents( True )
        printd( "ProcessEventsTask.run Number events to submit = ", len( toSubmit ) )
        for event in toSubmit:
            self.doSubmit( event )

def testSentinel1():
    printd( "testSentinel1: Start" )
    sentineld = SentinelDaemon()
    taskList = SentinelTaskList( GOVERNANCE_UPDATE_PERIOD_SECONDS )
    taskList.addTask( UpdateGovernanceTask() )
    taskList.addTask( CreateSuperblockTask() )
    taskList.addTask( AutoVoteTask() )
    sentineld.addTask( taskList )
    sentineld.addTask( ProcessEventsTask() )
    sentineld.run()

if __name__ == "__main__":

    govobjs = getGovernanceObjects()
    
    for (key,gobj) in govobjs.items():
        printd( "key = ", key )

    getMasternodes()

    printd( "My VIN: ", getMyVin() )

    testSentinel1()
