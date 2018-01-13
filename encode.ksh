function _replace {
	OLDIFS=$IFS
	IFS=$2
	str=""
	sections=0
	for section in $1; do ((sections=sections+1)); done
	i=0
	for section in $1
	do
		str=$str$section
		newStr=$str$3
		((i=i+1))
		if [[ $i -lt $sections ]]
		then
			str=$newStr
		fi
	done
	
	IFS=$OLDIFS
	echo $str
}
function replace {
	OLDIFS=$IFS
	IFS=""
	str=$1
	newStr=""
	while [ "$str" != "$newStr" ]
	do
		newStr=$str
		str=`_replace $1 $2 $3`
	done
	
	IFS=$OLDIFS
	echo $str
}
function jankyEncode {
	OLDIFS=$IFS
	IFS=""
	str=$1
	str=`replace $str 'x' 'x78'`
	str=`replace $str '!' 'x21'`
	str=`replace $str '"' 'x22'`
	str=`replace $str '#' 'x23'`
	str=`replace $str '$' 'x24'`
	str=`replace $str '%' 'x25'`
	str=`replace $str '&' 'x26'`
	str=`replace $str "'" 'x27'`
	str=`replace $str '(' 'x28'`
	str=`replace $str ')' 'x29'`
	str=`replace $str '+' 'x2B'`
	str=`replace $str ',' 'x2C'`
	str=`replace $str '-' 'x2D'`
	str=`replace $str '.' 'x2E'`
	str=`replace $str '/' 'x2F'`
	str=`replace $str ':' 'x3A'`
	str=`replace $str ';' 'x3B'`
	str=`replace $str '<' 'x3C'`
	str=`replace $str '=' 'x3D'`
	str=`replace $str '>' 'x3E'`
	str=`replace $str '?' 'x3F'`
	str=`replace $str '@' 'x40'`
	str=`replace $str '[' 'x5B'`
	str=`replace $str '\' 'x5C'`
	str=`replace $str ']' 'x5D'`
	str=`replace $str '^' 'x5E'`
	str=`replace $str '_' 'x5F'`
	str=$(replace $str '`' 'x60')
	str=`replace $str '{' 'x7B'`
	str=`replace $str '|' 'x7C'`
	str=`replace $str '}' 'x7D'`
	str=`replace $str '~' 'x7E'`
	str=`replace $str ' ' 'x20'`
	IFS=$OLDIFS
	echo $str
}

function segment {
	minSegmentSize=$1
	maxSegmentSize=$2
	idx=$3
	input=$4
	if [[ ${#input} -lt $maxSegmentSize ]]
	then
		echo -n "$idx.$input""x00"
		return 0
	fi
	len=0
	OLDIFS=$IFS
	IFS=" "
	PRINTABLE="0 1 2 3 4 5 6 7 8 9 a b c d e f g h i j k l m n o p q r s t u v w x y z A B C D E F G H I J K L M N O P Q R S T U V W X Y Z"
	for char in $PRINTABLE
	do
		OLDIFS2=$IFS
		IFS="$char"
		str=""
		found="0"
		for segment in $input
		do
			str=$str$segment$char
			if [[ ${#str} -gt minSegmentSize && ${#str} -lt maxSegmentSize ]]
			then
				echo "$idx.$str"
				((idx=idx+1))
				str=""
				found="1"
			fi
		done
		if [[ "$found" != "0" ]]
		then
			IFS=
			segment $minSegmentSize $maxSegmentSize $idx $str
			return 0
		fi
		IFS=$OLDIFS2
	done
	IFS=	
	IFS=$OLDIFS
}
OLDIFS=$IFS
IFS=""
input=$(cat)
str=`jankyEncode "$input"`
IFS=$OLDIFS
newstr=""
for line in $str
do
	newstr="$newstr${line}x0A"
done
segment 42 62 1 "${newstr}"
