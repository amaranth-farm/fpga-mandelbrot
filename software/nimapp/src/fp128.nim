import std/algorithm
import pkg/nint128
import strutils

const SCALE*           = 8 * 8
const BYTE_WIDTH*      = SCALE shr 3 + 8
const MAX_FRAC_DIGITS* = 20

proc strToFp128*(s: string): Int128 =
    if s == "": return i128(0)

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

    # cut off garbage digits
    frac = frac[0 ..<  min(19, len(frac))]

    let fraction =
        if len(frac) > 0:
            var exponent = i128(1)
            for i in 0 ..< len(frac):
                exponent *= i128(10)
            (frac.parseInt128() shl SCALE) div exponent
        else:
            i128(0)

    let absresult = whole.parseInt128 shl SCALE + fraction
    if negative: -absresult: else: absresult

proc fp128ToStr*(n: Int128): string =
    var sign = ""
    let absn = if (n < i128(0)): sign = "-"; -n else: n
    let whole = $(absn shr SCALE)
    let frac_mask = cast[Int128](u128(0xffffffffffffffff))
    var frac = absn and frac_mask

    # echo "n:    ", n.toHex
    # echo "absn: ", cast[UInt128](absn).toHex
    # echo "whole: " & whole
    # echo "frac: ", cast[UInt128](frac).toHex
    # echo "      " & "              998877665544332211"

    var str: string = ""
    var no_digits: int = 0
    while frac > i128(0):
        frac *= i128(10)
        let digit = $cast[byte]((frac shr SCALE) and i128(0xf))
        str = str & digit
        frac = frac and frac_mask
        inc(no_digits)
        if no_digits >= MAX_FRAC_DIGITS: break

    if len(str) > 0:
        sign & whole & '.' & str
    else:
        sign & whole

proc from_int*(x: int): Int128             = i128(x) shl SCALE
proc fp_mul*(x: Int128, y: Int128): Int128 = (x shr (SCALE div 2)) * (y shr (SCALE div 2))

proc test() =
    let negpi = cast[UInt128](strToFp128("-3.14159265359"))
    echo negpi.toHex()
    echo cast[UInt128](strToFp128("-1")).toHex()
    echo cast[UInt128](strToFp128("1")).toHex()
    echo cast[UInt128](strToFp128("1.25")).toHex()
    echo cast[UInt128](strToFp128("1.32")).toHex()
    echo "              998877665544332211"

    echo fp128ToStr(cast[Int128](negpi))
    echo fp128ToStr(strToFp128("-1"))
    echo fp128ToStr(strToFp128("1"))
    echo fp128ToStr(strToFp128("1.25"))
    echo fp128ToStr(strToFp128("1.32"))
    echo fp128ToStr(strToFp128("1.3333333333333333333"))
    echo fp128ToStr(strToFp128("0.0000000000000000001"))
    echo fp128ToStr(i128(1))
    echo fp128ToStr(strToFp128(""))

#test()
#quit()