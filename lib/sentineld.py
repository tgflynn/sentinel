#!/usr/bin/env python

"""
Module for the Sentinel Daemon
"""

import sys
import os

sys.path.append("lib")
sys.path.append("scripts") 

dir_path = os.path.dirname(os.path.realpath(__file__))

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

#from governance import Event
#from classes import Proposal, Superblock
from dashd import CTransaction, rpc_command

import time

GOVERNANCE_UPDATE_PERIOD_SECONDS = 30

# Number of blocks before a superblock to create superblock objects for
# auto vote.
#SUPERBLOCK_CREATION_DELTA = 10
SUPERBLOCK_CREATION_DELTA = 1

# Minimum number of absolute yes votes to include a proposal in a superblock
#PROPOSAL_QUORUM = 10
PROPOSAL_QUORUM = 0

# For testing, set to True in production
ENABLE_PROPOSAL_VALIDATION = False

# For testing, set to True in production
ENABLE_SUPERBLOCK_VALIDATION = True

OBJECT_TYPE_MAP = { govtypes.trigger: "trigger", govtypes.proposal: "proposal" }
OBJECT_TYPE_REVERSE_MAP = { "trigger": govtypes.trigger, "proposal": govtypes.proposal }

DB = libmysql.connect(config.hostname, config.username, config.password, config.database)

def computeHashValue( data ):
    m = hashlib.sha256()
    m.update( data )
    hex = m.hexdigest()
    return int( hex, 16 )

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
        sql += " where id = %s"
        return sql

    def getMemberSQL( self, cls, name ):
        if name not in cls.getColumns():
            raise Exception( "DBObject.getMemberSQL: ERROR Unknown field name: %s" % ( name ) )
        value = self.__dict__[name]
        if value is None:
            return "NULL"
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
        pass

    def load( self ):
        # Overridden in subclasses
        pass

    def storeInternal( self, cls ):
        data = self.getInstanceData( cls )
        if self.id is None:
            sql = cls.getInsertSQL()
        else:
            sql = cls.getUpdateSQL()
            data.append( self.id )
        c = libmysql.db.cursor()
        print "DBObject.storeInternal: sql = ", sql
        print "DBObject.storeInternal: data = ", data
        c.execute( sql, data )
        insertId = libmysql.db.insert_id()
        c.close()
        libmysql.db.commit()
        return insertId

    def loadInternal( self, cls ):
        if self.id is None:
            raise( Exception( "DBObject.loadInternal: ERROR id is NULL" ) )
        sql = cls.getSelectSQL()
        sql += "where %s" % ( cls.getIdColumn() )
        sql += " = %s"
        c = libmysql.db.cursor()
        c.execute( sql, ( self.id ) )
        row = c.fetchone()
        if row is None:
            raise( Exception( "DBObject.loadInternal: ERROR row not found for id = %s" % ( self.id ) ) )
        columns = cls.getColumns()
        if len( row ) != len( columns ):
            raise( Exception( "DBObject.loadInternal: ERROR incorrect row length" ) )
        for i in range( len( columns ) ):
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
                    'object_status' ]
        return columns

    @classmethod
    def getColumnSet( cls ):
        return frozenset( self.getColumns() )

    @staticmethod
    def getLocalColumns():
        localColumns = frozenset( [ 'id',
                                    'parent_id',
                                    'object_name',
                                    'object_status' ] )
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
        print "getJSON: jsonData = ", jsonData
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
        sql = GovernanceObject.getSelectSQL() + " where object_hash = %s"
        #print "existsInDb: sql = ", sql
        c = libmysql.db.cursor()
        c.execute( sql, ( self.object_hash ) )
        result = c.fetchone()
        c.close()
        if result is None:
            self.id = None
            return False
        else:
            self.id = result[0]
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
        localColumns = frozenset( [ 'id',
                                    'governance_object_id',
                                    'superblock_name' ] )
        return localColumns

    @staticmethod
    def getIdColumn():
        return 'governance_object_id'

    def store( self ):
        insertId = self.storeInternal( GovernanceObject )
        if self.governance_object_id is None:
            self.governance_object_id = insertId
        self.storeInternal( Superblock )
        if self.id is None:
            self.id = insertId
        self.governance_id = self.id

    def load( self ):
        self.loadInternal( GovernanceObject )
        self.loadInternal( Superblock )
        self.id = self.governance_object_id

    def isValid( self ):
        if not ENABLE_SUPERBLOCK_VALIDATION:
            return True
        sql = "select governance_object_id, object_status from superblock, governance_object where "
        sql += "event_block_height = %s and "
        sql += "( object_status = 'NEW-LOCAL' or object_status = 'SUBMITTED-LOCAL' )"
        c = libmysql.db.cursor()
        c.execute( sql, self.event_block_height )
        rows = c.fetchall()
        if len( rows ) != 1:
            # Something's wrong if this query returns more than 1 row and if it returns
            # no rows we have nothing to validate against so return False in both cases
            return False
        row = rows[0]
        localSuperblock = GFACTORY.createFromTable( 'trigger', row[0] )
        if localSuperblock.event_block_height != self.event_block_height:
            return False
        if localSuperblock.payment_addresses != self.payment_addresses:
            return False
        if localSuperblock.payment_amounts != self.payment_amounts:
            return False
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
        localColumns = frozenset( [ 'id',
                                    'governance_object_id',
                                    'proposal_name' ] )
        return localColumns

    @staticmethod
    def getIdColumn():
        return 'governance_object_id'

    def store( self ):
        insertId = self.storeInternal( GovernanceObject )
        if self.governance_object_id is None:
            self.governance_object_id = insertId            
        self.storeInternal( Proposal )
        if self.id is None:
            self.id = insertId

    def load( self ):
        self.loadInternal( GovernanceObject )
        self.loadInternal( Proposal )
        self.id = self.governance_object_id

    def isValid( self ):
        if not ENABLE_PROPOSAL_VALIDATION:
            return True
        # Check name
        if not re.match( r'^[a-zA-Z0-9]+$', self.proposal_name ):
            return False
        now = calendar.timegm( time.gmtime() )
        if self.end_epoch <= now:
            return False
        if self.end_epoch <= self.start_epoch:
            return False
        # TODO
        #  - Check that payment_address is a valid base58 encoded non-multisig Dash address
        #  - Check that payment_amount < budget allocation
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
        self.storeInternal( Event )

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

    def createFromTable( self, subtype, rowId ):
        govobj = self.create( subtype, None )
        govobj.id = rowId
        govobj.load()
        return govobj

    def createById( self, rowId ):
        print "GovernanceFactory.createById: rowId = ", rowId
        subtype = GovernanceObject.getObjectType( rowId )
        if subtype is None:
            return None
        govobj = self.createFromTable( subtype, rowId )
        return govobj

GFACTORY = GovernanceFactory()

class SentinelDaemon:

    def __init__( self ):
        self.nMainPeriodSeconds = 5
        self.tasks = []
    
    def addTask( self, task ):
        self.tasks.append( task )

    def runTasks( self ):
        print "SentinelDaemon.runTasks: Running tasks"
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
        print "UpdateGovernanceTask.run len( newobjs ) = ", len( newobjs )
        for obj in newobjs:
            if not obj.isValid():
                continue
            obj.object_status = "NEW-REMOTE"
            obj.store()

class CreateSuperblockTask(SentinelTask):

    def __init__( self ):
        SentinelTask.__init__( self )
        self.event_block_height = 0
        self.superblock = None

    def run( self ):
        print "CreateSuperblockTask.run START"
        self.superblock = None
        height = getBlockCount()
        cycle = getSuperblockCycle()
        diff = height % cycle
        self.event_block_height = height + diff
        print "CreateSuperblockTask: height = %d, cycle = %d, diff = %d" % ( height, cycle, diff )
        if ( cycle - diff ) != SUPERBLOCK_CREATION_DELTA:
            return
        # Check if we've already created this superblock
        if self.superblockCreated():
            print "CreateSuperblockTask.run Superblock already created, returning"
            return
        proposals = self.getNewProposalsRanked()
        print "CreateSuperblockTask.run Creating superblock"
        self.createSuperblock( proposals )
        if self.isElected():
            print "CreateSuperblockTask.run Submitting superblock"
            self.submitSuperblock()

    def isElected( self ):
        """Determine if we are the winner of the current superblock creator election"""
        blockHashVal = computeHashValue( getCurrentBlockHash() )
        myvin = getMyVin()
        if myvin is None:
            # If we're not a master we can't be elected
            print "isElected: We're not a masternode, returning False"
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
            print "isElected: No candidates, returning False"
            return False

        electedVin = candidates[0]['vin']

        print "isElected: electedVin = ", electedVin

        if electedVin == myvin:
            print "isElected: We're elected, returning True"
            return True

        #print "isElected: We're not elected, returning False"
        #return False
        print "isElected: We're not elected, returning True for testing"
        return True

    def submitSuperblock( self ):
        """Submit the superblock we created to the network"""
        if self.superblock is None:
            return
        # We just need to submit the event.  The ProcessEvents task
        # will do the rest of the work.
        event = Event( self.superblock.id )
        event.start_time = misc.get_epoch()
        event.store()
        print "CreateSuperblockTask.submitSuperblock Submitted event: ", str( event.__dict__ )
        self.superblock.object_status = "SUBMITTED-LOCAL"
        print "CreateSuperblockTask.submitSuperblock: Calling store, id = ", self.superblock.id
        self.superblock.store()
        
    def superblockCreated( self ):
        sql = "select object_status, event_block_height from governance_object, superblock where "
        sql += "governance_object.id = superblock.governance_object_id and "
        sql += "event_block_height = %s and "
        sql += "( object_status = 'NEW-LOCAL' or object_status = 'SUBMITTED-LOCAL' )"
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
        sql += "%s.governance_object_id, %s.object_status, %s.absolute_yes_count " % ( propTable, govTable, govTable )
        sql += "from %s, %s " % ( propTable, govTable )
        sql += "where %s.id = %s.governance_object_id and " % ( govTable, propTable )
        sql += "object_status = 'NEW-REMOTE' and "
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
        print "createSuperblock: Start, len( proposals ) = ", len( proposals )
        payments = []
        for proposal in proposals:
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
        print "createSuperblock: payment_addresses = ", payment_addresses
        print "createSuperblock: payment_amounts = ", payment_amounts
        superblock.payment_addresses = payment_addresses
        superblock.payment_amounts = payment_amounts
        superblock.object_status = "NEW-LOCAL"
        superblock.event_block_height = self.event_block_height
        superblock.updateObjectData()
        superblock.store()
        self.superblock = superblock

class VoteSuperblocksTask(SentinelTask):

    def __init__( self ):
        SentinelTask.__init__( self )

    def run( self ):
        pass

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
            event.id = row[0]
            event.load()
            events.append( event )
        return events
        
    def doPrepare( self, event ):
        print "doPrepare: event = ", event.__dict__
        govobj = GFACTORY.createById( event.governance_object_id )
        print "doPrepare: govobj = ", govobj.__dict__
        cmd = "gobject prepare %(object_parent_hash)s %(object_revision)s %(object_creation_time)s %(object_name)s %(object_data)s" % govobj.__dict__

        print "doPrepare: cmd = ", cmd

        result = rpc_command( cmd )

        print "doPrepare: result = ", result

        if misc.is_hash( result ):
            hashtx = misc.clean_hash( result )
            print " -- got hash:", hashtx
            govobj.object_fee_tx = hashtx
            print "doPrepare: Calling govobj.store, govobj =  ", govobj.__dict__
            govobj.store()
            event.prepare_time = misc.get_epoch()
            event.store()
        else:
            print " -- got error:", result
            event.error_time = misc.get_epoch()
            # separately update event error message
            event.error_message = result
            event.store()

    def doSubmit( self, event ):
        govobj = GFACTORY.createById( event.governance_object_id )
        cmd = "gobject submit %(object_fee_tx)s %(object_parent_hash)s %(object_revision)s %(object_creation_time)s %(object_name)s %(object_data)s" % govobj.__dict__

        print "doSubmit: cmd = ", cmd

        if not misc.is_hash( govobj.object_fee_tx ):
            print "doSubmit: Warning no object_fee_tx hash"
            return

        result = rpc_command( cmd )

        print "doSubmit: result = ", result

        if misc.is_hash( result ):
            event.submit_time = misc.get_epoch()
            event.store()
        # If the submit call did not succeed assume more confirmations needed
        # so we will try again later.
        # TODO: Check for other errors here and set the error fields

    def run( self ):
        print "ProcessEventsTask.run START"
        toPrepare = self.getEvents( False )
        print "ProcessEventsTask.run Number events to prepare = ", len( toPrepare )
        for event in toPrepare:
            self.doPrepare( event )

        toSubmit = self.getEvents( True )
        print "ProcessEventsTask.run Number events to submit = ", len( toSubmit )
        for event in toSubmit:
            self.doSubmit( event )

def testSentinel1():
    print "testSentinel1: Start"
    sentineld = SentinelDaemon()
    taskList = SentinelTaskList( GOVERNANCE_UPDATE_PERIOD_SECONDS )
    taskList.addTask( UpdateGovernanceTask() )
    taskList.addTask( CreateSuperblockTask() )
    sentineld.addTask( taskList )
    sentineld.addTask( ProcessEventsTask() )
    sentineld.run()

if __name__ == "__main__":

    govobjs = getGovernanceObjects()
    
    for (key,gobj) in govobjs.items():
        print "key = ", key

    getMasternodes()

    print "My VIN: ", getMyVin()

    testSentinel1()
