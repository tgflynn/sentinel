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
#import crontab
import cmd, sys
import govtypes
import random 
import json 
import time
import datetime


#from governance import GovernanceObject, GovernanceObjectMananger, Setting, Event
#from classes import Proposal, Superblock
from dashd import CTransaction, rpc_command

import time

GOVERNANCE_UPDATE_PERIOD_SECONDS = 30

# Number of blocks before a superblock to create superblock objects for
# auto vote.
SUPERBLOCK_CREATION_DELTA = 10

# Minimum number of absolute yes votes to include a proposal in a superblock
PROPOSAL_QUORUM = 10

DB = libmysql.connect(config.hostname, config.username, config.password, config.database)


def getGovernanceObjects():
    result = rpc_command( "gobject list" )
    print "result = ", result
    govobjs = json.loads( result )
    return govobjs

def getBlockCount():
    result = rpc_command( "getblockcount" )
    return int( result )

def getSuperblockCycle():
    # TODO: Add dashd rpc call for this
    # For now return the testnet value
    return 24

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

class GovernanceObject:

    def __init__( self, name ):
        for cname in self.getColumns():
            self.__dict__[cname] = None
        self.object_name = name
        self.object_revision = govtypes.FIRST_REVISION
        self.subtype = None

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

    @staticmethod
    def getColumnSet():
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
        objpair = [ self.subtype, obj ]
        return json.dumps( objpair, sort_keys = True )

    def getJSONHex( self ):
        hexdata = binascii.hexlify( self.getJSON() )
        return hexdata
        
    def loadJSONFields( self, rec ):
        objpair = json.loads( binascii.unhexlify( rec['DataHex'] ) )
        objrec = objrec[1]
        columns = self.getColumns()
        localColumns = self.getLocalColumns()
        for cname in columns:
            if cname in localColumns:
                continue
            value = objrec[cname]
            setattr( self, cname, value )

    def getJSONFields( self ):
        obj = {}
        columns = self.getColumns()
        localColumns = self.getLocalColumns()
        for cname in columns:
            if cname in localColumns:
                continue
            obj[cname] = getattr( self, cname )
        return obj

    def getMemberSQL( self, name ):
        if name not in self.getColumns():
            raise Exception( "GovernanceObject.getMemberSQL: ERROR Unknown field name: %s" % ( name ) )
        value = self.__dict__[name]
        if value is None:
            return "NULL"
        return value

    def getSelectList( self ):
        selectList = ""
        columns = self.getColumns()
        for i in range( len( self.getColumns() ) ):
            cname = columns[i]
            selectList += cname
            if i < ( len( columns ) - 1 ):
                selectList += ", "
        return selectList

    def getSelectSQL( self ):
        sql = "select " + getSelectList()
        sql += " from " + self.getTableName() + " "
        return sql

    def getInsertSQL( self ):
        sql = "insert into %s ( " % ( self.getTableName() )
        columns = self.getColumns()
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

    def getUpdateSQL( self ):
        columns = self.getColumns()
        sql = "update %s set " % ( self.getTableName() )
        for i in range( 1, len( columns ) ):
            cname = columns[i]
            sql += cname + " = %s"
            if i < ( len( columns ) - 1 ):
                sql += ", "
        sql += " where id = %s"
        return sql

    def getInstanceData( self ):
        data = []
        columns = self.getColumns()
        for cname in columns[1:]:
            data.append( self.getMemberSQL( cname ) )
        return data

    def existsInDb( self ):
        if self.hash.empty():
            return False
        sql = self.getSelectSQL() + " where object_hash = %s"
        c = libmysql.db.cursor()
        c.execute( sql, ( self.hash ) )
        result = c.fetchone()
        c.close()
        if result is None:
            self.id = None
            return False
        else:
            self.id = result[0]
            return True

    def store( self ):
        self.storeInternal()

    def load( self ):
        self.loadInternal()

    def storeInternal( self ):
        if self.id is None:
            sql = self.getInsertSQL()
        else:
            sql = self.getUpdateSQL()
        data = self.getInstanceData()
        c = libmysql.db.cursor()
        c.execute( sql, data )
        c.close()

    def loadInternal( self ):
        if self.id is None:
            raise( Exception( "GovernanceObject.loadInternal: ERROR id is NULL" ) )
        sql = self.getSelectSQL()
        sql += "where %s" % ( self.getIdColumn() )
        sql += " = %s"
        c = libmysql.db.cursor()
        c.execute( sql, ( self.id ) )
        row = c.fetchone()
        columns = self.getColumns()
        if len( row ) != len( columns ):
            raise( Exception( "GovernanceObject.loadInternal: ERROR incorrect row length" ) )
        for i in range( len( columns ) ):
            setattr( self, columns[i], row[i] )

    def isValid( self ):
        # Base class objects aren't valid
        return False
    
class Superblock(GovernanceObject):

    def __init__( self, name ):
        GovernanceObject.__init__( self, name )
        self.subtype = govtypes.trigger
        self.tableName = "superblock"

    @staticmethod
    def getTableName( self ):
        return "superblock"

    @staticmethod
    def getColumns( self ):
        columns = [ 'id', 
                    'governance_object_id',
                    'superblock_name',
                    'event_block_height',
                    'payment_addresses',
                    'payment_amounts' ]
        return columns

    @staticmethod
    def getLocalColumns( self ):
        localColumns = frozenset( [ 'id',
                                    'governance_object_id',
                                    'superblock_name' ] )
        return localColumns

    @staticmethod
    def getIdColumn():
        return 'governance_object_id'

    def store( self ):
        GovernanceObject.storeInternal( self )
        self.storeInternal()

    def load( self ):
        GovernanceObject.storeInternal( self )
        self.loadInternal()

    def isValid( self ):
        return False

class Proposal(GovernanceObject):

    def __init__( self, name ):
        GovernanceObject.__init__( self, name )
        self.subtype = govtypes.proposal
        self.tableName = "proposal"

    @staticmethod
    def getTableName( self ):
        return "proposal"

    @staticmethod
    def getColumns( self ):
        columns = [ 'id', 
                    'governance_object_id',
                    'proposal_name',
                    'start_epoch',
                    'end_epoch',
                    'payment_address',
                    'payment_amount' ]
        return columns

    @staticmethod
    def getLocalColumns( self ):
        localColumns = frozenset( [ 'id',
                                    'governance_object_id',
                                    'proposal_name' ] )
        return localColumns

    @staticmethod
    def getIdColumn():
        return 'governance_object_id'

    def store( self ):
        GovernanceObject.storeInternal( self )
        self.storeInternal()

    def load( self ):
        GovernanceObject.loadInternal( self )
        self.loadInternal()

    def isValid( self ):
        return False

class GovernanceFactory:

    def __init__( self ):
        pass

    def create( self, subtype, name ):
        govobj = None
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

GFACTORY = GovernanceFactory()

class SentinelDaemon:

    def __init__( self ):
        self.nMainPeriodSeconds = 5
        self.tasks = []
    
    def addTask( self, task ):
        self.tasks.append( task )

    def runTasks( self ):
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

class SentinelTaskList:

    """Represents a list of tasks tha should be run sequentially in order"""

    def __init__( self, nPeriodSeconds ):
        SentinelTask.__init__( self, nPeriodSeconds )
        self.taskList = []
    
    def addTask( self, task ):
        self.taskList.append( task )

    def run( self ):
        for task in self.taskList:
            self.task.run()
    
class UpdateGovernanceTask:

    def __init__( self ):
        SentinelTask.__init__( self, GOVERNANCE_UPDATE_PERIOD_SECONDS )

    def run( self ):
        govobjs = getGovernanceObjects()
        newobjs = []
        for key, rec in govobjs.items():
            subtype = rec['DataString'][0]
            name = rec['Name']
            govobj = GFACTORY.create( subtype, name )
            govobj.loadJSON( rec )
            if not govobj.existsInDb():
                newobjs.append( govobj )
        for obj in newobjs:
            if not obj.isValid():
                continue
            obj.object_status = "NEW-REMOTE"
            obj.save()

class CreateSuperblockTask:

    def __init__( self ):
        SentinelTask.__init__( self )

    def run( self ):
        height = getBlockCount()
        cycle = getSuperblockCycle()
        diff = height % cycle
        if ( cycle - diff ) != SUPERBLOCK_CREATION_DELTA:
            return
        proposals = self.getNewProposalsRanked()
        self.createSuperblock( proposals )
            
    def getNewProposalsRanked( self ):
        govTable = GovernanceObject.getTableName()
        propTable = Proposal.getTableName()
        sql = "select "
        sql += "%s.id, %s.object_status, %s.absolute_yes_count " % ( proptable, govTable, govTable )
        sql += "from %s, %s " % ( propTable, govTable )
        sql += "where %s.id = %s.governance_object_id and " % ( govTable, propTable )
        sql += "object_status = NEW_REMOTE and "
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
        payments = []
        for proposal in proposals:
            payment = { 'address': proposal.payment_address,
                        'amount': proposal.payment_amount }
            payments.append( payment )
        sbname = "sb" + str(random.randint(1000000, 9999999))
        superblock = GFACTORY.create( 'trigger', sbname )
        payment_addresses = ""
        payment_amounts = ""
        for i in range( len( payments ) ):
            payment = payments[i]
            payment_addresses += payment['address']
            payment_amounts += payment['amount']
            if i < ( len( payments ) - 1 ):
                payment_addresses += "|"
                payment_amounts += "|"
        superblock.payment_address = payment_addresses
        superblock.payment_amounts = payment_amounts
        superblock.object_status = "LOCAL"
        superblock.store()

class VoteSuperblocksTask:

    def __init__( self ):
        SentinelTask.__init__( self )

    def run( self ):
        pass


if __name__ == "__main__":

    govobjs = getGovernanceObjects()
    
    for (key,gobj) in govobjs.items():
        print "key = ", key
