#!/usr/bin/env python3
__all__=("bind", "bindVarsToFunc", "modifyCode", "UnbindableException")
__author__="KOLANICH"
__license__="Unlicense"
__copyright__=r"""
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org/>
"""

from sys import version_info
from types import CodeType, FunctionType
import dis, opcode
from collections import namedtuple, OrderedDict
from struct import pack
from inspect import currentframe
import re
from collections import defaultdict

CODE_PROP_PREFIX="co_"
codeArgs=("argcount", "kwonlyargcount", "nlocals", "stacksize", "flags", "codestring", "constants", "names", "varnames", "filename", "name", "firstlineno", "lnotab", "freevars", "cellvars")

def modifyCode(c:CodeType, patch:dict):
	"""Used to apply a patch to code object"""
	kwargs=OrderedDict()
	for pN in codeArgs:
		aN=CODE_PROP_PREFIX+pN
		if hasattr(c, aN):
			kwargs[pN]=getattr(c, aN)
		elif hasattr(c, pN):
			kwargs[pN]=getattr(c, pN)
		else:
			kwargs[pN]=None
	for pN, v in patch.items():
		kwargs[pN]=v
	#print(kwargs)
	return CodeType(*kwargs.values()) #**kwargs don't work here

lc=opcode.opmap["LOAD_CONST"]
ld=opcode.opmap["LOAD_DEREF"]
lg=opcode.opmap["LOAD_GLOBAL"]
lf=opcode.opmap["LOAD_FAST"]
lcl=opcode.opmap["LOAD_CLOSURE"]
lat=opcode.opmap["LOAD_ATTR"]
ln=opcode.opmap["LOAD_NAME"]

#loadInstrs={v for k,v in opcode.opmap.items() if k.find("LOAD")>=0}
loadInstrs={ld, lg, ln, lf, lcl}

opcVarCollMappingInitial={
	#tuple(opcode.hasfree):"freevars",
	tuple((v for k,v in opcode.opmap.items() if k.find("DEREF")>=0)):"freevars",
	tuple(opcode.hasname):"names",
	#tuple(opcode.haslocal):"varnames",
	#(lcl,):"cellvars"
}

opcVarCollMapping={}
for opcs, v in opcVarCollMappingInitial.items():
	for k in opcs:
		opcVarCollMapping[k]=v

def resolveOpcode(key):
	if isinstance(key, str):
		key=dis.opmap[key]
	return key

if version_info.minor >= 6:
	INSTR_PACK_STR="<BB"
elif version_info.minor < 6:
	INSTR_PACK_STR="<BH"

def genLoadInstr(opcode, arg):
	return pack(INSTR_PACK_STR, opcode, arg)
INSTR_WIDTH=len(genLoadInstr(0, 0))

class SymbolBuffer:
	"""Every load instruction corresponds to a buffer where it stores names. This represents a buffer tied to that instruction."""
	def __init__(self, opcodes:(tuple, set), buffer:(tuple, list)):
		self.opcodes=set(opcodes)
		self.buffer=dict(enumerate(buffer))
	
	def __getitem__(self, key:(int)):
		return self.buffer[key]

	def __contains__(self, key:(int)):
		return key in self.buffer
	
	def __delitem__(self, key:(int)):
		del(self.buffer[key])
	
	def __getattr__(self, key):
		return getattr(self.buffer, key)
	
	def __repr__(self):
		return "".join((self.__class__.__name__,"(",repr(self.buffer),")"))

class InlineAccountingSymbolBuffer(SymbolBuffer):
	def __init__(self, opcode:(tuple, set), buffer:(tuple, list), name=None, offset=0):
		super().__init__(opcode, buffer)
		self.maxArg=len(buffer)
		self.name=name
		self.inlined={}
		self.remaps={}
		self.offset=offset
		self.updateRemaps()
	def updateRemaps(self, begin=0):
		if self.buffer:
			self.remaps=dict(zip(self.buffer.keys(), range(self.offset, self.offset+len(self.buffer))))
	def __repr__(self):
		return "".join((self.__class__.__name__,"(",repr(self.buffer),", ",repr(self.remaps),", ",repr(self.name),")"))

	def __getitem__(self, key:(int, str)):
		return super().__getitem__(resolveOpcode(key)+self.offset)

	def __delitem__(self, key:(int)):
		 super().__delitem__(resolveOpcode(key)+self.offset)

	
	def __contains__(self, key:(int, str)):
		return super().__contains__(resolveOpcode(key)+self.offset)

class FuncScope(dict):
	"""The set of buffers with symbols names every function and/or its code object has."""
	def __init__(self, cd:CodeType, symbolBufferConstructor=None):
		super().__init__()
		if symbolBufferConstructor is None:
			symbolBufferConstructor=InlineAccountingSymbolBuffer
		for opcodes, propName in opcVarCollMappingInitial.items():
			propName=CODE_PROP_PREFIX+propName
			v=getattr(cd, propName)
			buffer=symbolBufferConstructor(opcodes, v, propName)
			for opc in opcodes:
				self[opc]=buffer
		#print(self.buffers)
		#self.cd=cd
	
	def __getitem__(self, key:(int, str)):
		return super().__getitem__(resolveOpcode(key))
	
	def __contains__(self, key:(int, str)):
		return super().__contains__(resolveOpcode(key))
	
	def __repr__(self):
		return "".join((self.__class__.__name__, "(", repr({opcVarCollMapping[k]:v for k,v in super().items()}), ")"))

class UnbindableException(Exception):
	pass

ignoredVariables=set(dir(FunctionType))
def getCallerContext(captureGlobals=False):
	f=currentframe()
	ctx=f.f_back.f_back.f_globals if captureGlobals else {}
	ctx.update(f.f_back.f_back.f_locals)
	del(f)
	return {k:v for k,v in ctx.items() if k not in ignoredVariables}

def bindVarsToFunc(f:FunctionType, inlines:dict=None, returnInfo=False):
	"""An implementition of inliner. f is function, inlines is dict of variables to inline, when returnInfo is True instead of function this returns a tuple (FuncScope, modified bytecode, inlined version of function)"""
	if inlines is None:
		inlines=getCallerContext()
	#print(inlines.keys())
	cd=f.__code__
	bcode=bytearray(cd.co_code)
	
	consts=list(cd.co_consts)
	clos=dict(enumerate(f.__closure__)) if f.__closure__ else {}
	scope=FuncScope(cd)
	scope[ld].offset=len(cd.co_cellvars)
	scope[ld].updateRemaps()
	#print(scope)
	#dis.dis(f)
	parsedBytecode=dis.Bytecode(cd)

	toInlineCands=defaultdict(set)
	for instr in parsedBytecode: #first pass: collecting names with load instrs
		opc=instr.opcode
		if opc in scope:
			arg=instr.arg
			symbolsBuf=scope[opc]
			if arg in symbolsBuf:
				toInlineCands[symbolsBuf[arg]].add(opc)
	#toInlineCands={name:opcs-loadInstrs for name, opcs in toInlineCands.items() if len(opcs&loadInstrs) and name in inlines.keys() }
	toInlineCands={name:opcs-loadInstrs for name, opcs in toInlineCands.items() if name in inlines.keys() }

	for symbolsBuf in scope.values():
		toInline=[it for it in symbolsBuf.items() if it[1] in toInlineCands.keys()]
		toInline.sort(key=lambda it: it[0])
		for arg, varName in toInline:
			if lat not in toInlineCands[varName]:
			 	del(symbolsBuf[arg])
			if ld in symbolsBuf.opcodes:
				del(clos[arg])
			symbolsBuf.inlined[arg+symbolsBuf.offset]=len(consts)
			consts.append(inlines[varName])
		symbolsBuf.updateRemaps()
	#print(scope)

	for instr in parsedBytecode:
		opc=instr.opcode
		if opc in scope:
			arg=instr.arg
			symbolsBuf=scope[opc]
			if arg in symbolsBuf.inlined:
				if opc not in loadInstrs: # it's not a load
					if arg not in symbolsBuf: # name moved to consts entirely
						raise UnbindableException("Inlined variable `"+getattr(cd, symbolsBuf.name)[arg]+"` (from buffer `"+symbolsBuf.name+"`) was touched in the way other than load ("+opcode.opname[opc]+")!")
					elif arg in symbolsBuf.remaps: # name is used for another purpose like load_attr
						arg=symbolsBuf.remaps[arg]
				else: #it's load, replace with load_const
					arg=symbolsBuf.inlined[arg]
					opc=lc
			elif arg in symbolsBuf.remaps:
				#print(symbolsBuf, arg, instr)
				arg=symbolsBuf.remaps[arg]
			bcode[instr.offset:instr.offset+INSTR_WIDTH]=genLoadInstr(opc, arg)
	
	#print(scope)
	patch={
		opcVarCollMapping[opc]:tuple(symbolsIndexRemap.values())
		for opc, symbolsIndexRemap in scope.items()
	} 
	patch["constants"]=tuple(consts)
	patch["codestring"]=bytes(bcode)
	cd=modifyCode(cd, patch)
	
	newFunc=FunctionType(cd, f.__globals__, f.__name__, f.__defaults__, tuple(clos.values()))
	newFunc.__doc__=f.__doc__
	if returnInfo:
		return (scope, bcode, newFunc)
	return newFunc

def bind(*args, **kwargs):
	"""Inlines variables into a function passed.
	4 ways to call
	* passing a func explicitly, as to inlineFunc:
		bind(func, {"inline_me":1})
	* as a decorator with a dict
		@bind({"inline_me":1})
	* as a decorator with kwargs
		@bind(inline_me=1)
	* as a decorator with implicit context capture
		@bind
	"""
	inlines=None
	if len(args) == 1:
		if isinstance(args[0], dict):
			inlines=args[0]
		elif isinstance(args[0], FunctionType):
			inlines=getCallerContext()
			return bindVarsToFunc(args[0], inlines)
	elif kwargs and not len(args):
		inlines=kwargs
		kwargs={}
	if inlines is not None:
		def dec(f:FunctionType):
			return bindVarsToFunc(f, inlines, **kwargs)
		return dec
	else:
		return bindVarsToFunc(*args, **kwargs)

selfBind=True
if selfBind:
	genLoadInstr=bindVarsToFunc(genLoadInstr)
	modifyCode=bindVarsToFunc(modifyCode)
	getCallerContext=bindVarsToFunc(getCallerContext)
	#dis.dis(bindVarsToFunc)
	bindVarsToFunc=bindVarsToFunc(bindVarsToFunc)
	#dis.dis(bindVarsToFunc)
	#bindVarsToFunc=bindVarsToFunc(bindVarsToFunc, {"modifyCode":modifyCode, "genLoadInstr":genLoadInstr})
	bind=bindVarsToFunc(bind)
	#dis.dis(bind.__code__.co_code)
	pass
