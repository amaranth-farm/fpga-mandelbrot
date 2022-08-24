import std/algorithm
import pkg/nint128
import strutils

const SCALE      = 8 * 8
const BYTE_WIDTH = SCALE shr 3 + 8

proc strToFp128*(s: string): UInt128 =
    var
        abs:   string
        whole: string
        frac:  string

    let negative = s.startsWith('-')
    abs = if negative: s.substr(1) else: s

    let parts = abs.split('.')
    case len(parts):
        of 1:
            whole = parts[0]
        of 2:
            whole = parts[0]
            frac  = parts[1]
        else:
            raise newException(OSError, "could not parse number")

    let fraction =
        if len(frac) > 0:
            var exponent = u128(1)
            for i in 0..<len(frac):
                exponent *= u128(10)
            (frac.parseUInt128() shl SCALE) div exponent
        else:
            u128(0)

    let absresult = whole.parseUInt128 shl SCALE + fraction
    if negative:
        return not absresult + 1
    return absresult

proc fp128ToStr*(n: UInt128): string =
    let sn = cast[Int128](n)
    var sign = ""
    let absn = if (sn < i128(0)): sign = "-"; -sn else: sn
    let whole = $(absn shr SCALE)
    let frac_mask = cast[Int128](u128(0xffffffffffffffff))
    var frac = absn and frac_mask

    # echo "n:    ", n.toHex
    # echo "absn: ", cast[UInt128](absn).toHex
    # echo "whole: " & whole
    # echo "frac: ", cast[UInt128](frac).toHex
    # echo "      " & "              998877665544332211"

    var str: string = ""
    while frac > i128(0):
        frac *= i128(10)
        let digit = $cast[byte]((frac shr SCALE) and i128(0xf))
        str = str & digit
        frac = frac and frac_mask

    if len(str) > 0:
        sign & whole & '.' & str
    else:
        sign & whole

proc test() =
    let negpi = strToFp128("-3.14159265359")
    echo negpi.toHex()
    echo strToFp128("-1").toHex()
    echo strToFp128("1").toHex()
    echo strToFp128("1.25").toHex()
    echo strToFp128("1.32").toHex()
    echo "              998877665544332211"

    echo fp128ToStr(negpi)
    echo fp128ToStr(strToFp128("-1"))
    echo fp128ToStr(strToFp128("1"))
    echo fp128ToStr(strToFp128("1.25"))
    echo fp128ToStr(strToFp128("1.32"))
