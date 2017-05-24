#!/usr/bin/env python3
import itertools
from collections import OrderedDict
from keyword import kwlist
from argparse import *
kwset=set(kwlist)

def varsNamesGen(alph, l=255):
	i=0
	j=1
	while True:
		for name in map(lambda x: "".join(x), itertools.combinations(alph, j)):
			if name not in kwset:
				yield name
				i+=1
				if i>l:
					return
		j+=1

def genVarNames(len=255):
	a=ord("a")
	alphabetLen=26
	alphabet=[chr(i) for i in range(a, a+alphabetLen)]
	a=ord("A")
	alphabet.extend([chr(i) for i in range(a, a+alphabetLen)])
	return list(varsNamesGen(alphabet, len))

def genFunc(name, varNames, indent=0):
	return "\n".join((
		"\t"*indent+"def "+name+"():",
		"\t"*(indent+1)+"return "+"+".join(varNames),
		""
	))

def genVarsInitializer(varsDict, indent=0):
	return "\n".join((indent*"\t"+"=".join(i) for i in varsDict.items()))+"\n"

def genMeasuredFunc(name, varsDict, indent=0):
	return "".join((
		genFunc(name, varsDict.keys(), indent),
		genVarsInitializer(varsDict, indent),
		"\t"*indent+name+"_inlined=bind.bind("+name+", locals())"
	))

def genClosureMeasuredFunc(name, varsDict, innerName=None, indent=0):
	if innerName is None:
		innerName="inner_"+name
	return "\n".join((
		"\t"*indent+"def "+name+"_gen():",
		genMeasuredFunc(innerName, varsDict, indent+1),
		"\t"*(indent+1)+"return ("+innerName+", "+innerName+"_inlined)\n",
		indent*"\t"+"("+name+", "+name+ "_inlined)="+name+"_gen()",
		""
	))

def genMeasurement(name):
	return "\n".join((
		measResultVarName+"['"+name+"']=OrderedDict((",
		"\t('orig'	, timeit.timeit("+name+"			  )),",
		"\t('inlined', timeit.timeit("+name+"_inlined)),",
		"))"
	))

def genDis(name):
	return "dis.dis("+name+")"

measResultVarName="measResults"
preamble=r"""
import dis, json, timeit, bind
from collections import OrderedDict

def computeDelta(res):
	for i in res:
		res[i]["% faster"]=(res[i]["orig"]-res[i]["inlined"])/res[i]["orig"]*100

"""+ measResultVarName+"={}"

if __name__ == "__main__":
	argp=ArgumentParser(
		description="Generates code for benchmarking the library"
	)
	argp.add_argument("--count", type=int, help="Count of variables per function to be inlined", default=0xff)
	args=argp.parse_args()

	varNames=genVarNames(args.count)
	varsDict=dict(zip(varNames, map(str, range(len(varNames)))))

	text="\n".join((
		preamble,
		genClosureMeasuredFunc("load_deref", varsDict),
		genMeasuredFunc("load_global", varsDict),
		genMeasurement("load_global"),
		genMeasurement("load_deref"),
		"computeDelta("+measResultVarName+")",
		"print(json.dumps("+measResultVarName+", indent='\t'))"
	))
	print(text)
