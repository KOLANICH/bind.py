#!/usr/bin/env python3
import os, sys
import unittest
import itertools, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from bind import *

from collections import OrderedDict
dict=OrderedDict

from io import StringIO

from types import CodeType
import dis

def justDis(co):
	disBuff=StringIO()
	dis._disassemble_bytes(
		code=co.co_code,
		varnames=co.co_varnames,
		names=co.co_names,
		constants=co.co_consts,
		cells=(co.co_cellvars+co.co_freevars),
		file=disBuff
	)
	return disBuff.getvalue()

class Tests(unittest.TestCase):
	maxDiff=None

	def assertEqual(self, a, b, *args, **kwargs):
		if isinstance(a, CodeType) and isinstance(b, CodeType):
			a=justDis(a)
			b=justDis(b)
		super().assertEqual(a, b, *args, **kwargs)

a=1
b=2
class SimpleTest(Tests):
	def ref(*args, **kwargs):
		x=1
		y=2
		return (x, y) # if just (a, b) python loads whole tuple
	def proto(*args, **kwargs):
		x=a
		y=b
		return (x, y)
	
	def testNotSpoilsSimple(self):
		def a(*args, **kwargs):
			print(args, kwargs)
		@bind
		def b(*args, **kwargs):
			print(args, kwargs)
		self.assertEqual(a.__code__, b.__code__)
	
	def testExplicitlySpecifiedInline(self):
		explicitlySpecifiedInline=bind(self.__class__.proto, {"a":1, "b":2})
		self.assertEqual(self.__class__.ref.__code__, explicitlySpecifiedInline.__code__)
		self.assertEqual(self.__class__.ref(), explicitlySpecifiedInline())
	
	def testPartialInline(self):
		partialInline=bind(self.__class__.proto, {"x":100, "y":500})
		partialInline=bind(partialInline, {"a":1})
		partialInline=bind(partialInline, {"b":2})
		self.assertEqual(self.__class__.ref.__code__, partialInline.__code__)
		self.assertEqual(self.__class__.ref(), partialInline())
	
	
	
	def testCaptureContextInline(self):
		a=1
		b=2
		localsInline=bind(self.__class__.proto)
		self.assertEqual(self.__class__.ref.__code__, localsInline.__code__)
		self.assertEqual(self.__class__.ref(), localsInline())
	
	def testGlobalsInline(self):
		gls=globals()
		gls.update(locals())
		globalsInline=bind(self.__class__.proto, gls)
		self.assertEqual(self.__class__.ref.__code__, globalsInline.__code__)
		self.assertEqual(self.__class__.ref(), globalsInline())
	
	def testDecoratorKwargs(self):
		@bind(a=1, b=2)
		def a(*args, **kwargs):
			x=a
			y=b
			return (x, y)
		#self.assertEqual(self.__class__.ref.__code__, a.__code__)
		self.assertEqual(a(), self.__class__.ref())
	
	def testDecoratorExplicitlySpecified(self):
		@bind({"a":1, "b":2})
		def b(*args, **kwargs):
			x=a
			y=b
			return (x, y)
		#self.assertEqual(self.__class__.ref.__code__, b.__code__)
		self.assertEqual(self.__class__.ref(), b())
	
	def testDecoratorCaptureContext(self):
		a=1
		b=2
		@bind
		def c(*args, **kwargs):
			x=a
			y=b
			return (x, y)
		self.assertEqual(self.__class__.ref.__code__, c.__code__)
		self.assertEqual(self.__class__.ref(), c())
	
class ControlFlowTest(Tests):
		def testLoopTuple(self):
			def ref():
				s=0
				for a in (1,2,3):
					s+=a
				return s
			@bind(b=(1,2,3))
			def inl():
				s=0
				for a in b:
					s+=a
				return s
			#self.assertEqual(ref.__code__, inl.__code__)
			self.assertEqual(ref(), inl())
		def testLoopList(self):
			def ref():
				s=0
				for a in [1,2,3]:
					s+=a
				return s
			@bind(b=[1,2,3])
			def inl():
				s=0
				for a in b:
					s+=a
				return s
			#self.assertEqual(ref.__code__, inl.__code__)
			self.assertEqual(ref(), inl())

		def testLoopRange(self):
			def ref():
				s=0
				for a in range(3):
					s+=a
				return s
			@bind(b=range(3))
			def inl():
				s=0
				for a in b:
					s+=a
				return s
			#self.assertEqual(ref.__code__, inl.__code__)
			self.assertEqual(ref(), inl())

		def testIfElse(self):
			def ref(c):
				if c:
					s=2
				else:
					s=1
				return s
			@bind(a=2, b=1)
			def inl(c):
				if c:
					s=a
				else:
					s=b
				return s
			self.assertEqual(ref.__code__, inl.__code__)
			self.assertEqual(ref(True), inl(True))
			self.assertEqual(ref(False), inl(False))

		def testEmbeddedFunction(self):
			def ref():
				def a():
					return b
				b=10
				return a()
			#dis.dis(ref)
			inl=bind(ref, {"b":1})
			#self.assertEqual(ref.__code__, inl.__code__)
			self.assertEqual(ref(), inl())
			self.assertEqual(ref(), inl())

		def testUnbindableReadWriteGlobal(self):
			alpha=2
			with self.assertRaises(UnbindableException):
				@bind
				def ref():
					global alpha
					alpha=alpha+10

		def testUnbindableWriteReadGlobal(self):
			alpha=2
			with self.assertRaises(UnbindableException):
				@bind
				def ref():
					global alpha
					alpha=10
					return alpha

		def testUnbindableWriteGlobal(self):
			alpha=2
			with self.assertRaises(UnbindableException):
				@bind
				def ref():
					global alpha
					alpha=10







if __name__ == '__main__':
	unittest.main()
