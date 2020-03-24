#include <stdlib.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <sys/signal.h>
#include <sys/types.h>

#define _POSIX_SOURCE 1         //POSIX compliant source

/*
  Simple C program to read serial port data from a Boltek EFM-100 
  atmospheric electric field monitor and printing out the electric 
  field and it change.
*/

const int sentenceSize = 14;

int readyPort(char *portName) {
	int fd;
	struct termios options; 
	
	fd = open(portName, O_RDONLY | O_NOCTTY | O_NONBLOCK);
	if( fd < 0 ) {
		return(-1);
	}
	
	fcntl(fd, F_SETFL, FNDELAY);
	tcgetattr(fd, &options);
	cfsetispeed(&options, B9600);
	cfsetospeed(&options, B9600);

	options.c_cflag |= (CLOCAL | CREAD);
	options.c_cflag &= ~PARENB;
	options.c_cflag &= ~CSTOPB;
	options.c_cflag &= ~CSIZE;
	options.c_cflag |= CS8;
	options.c_iflag |= (IXON | IXOFF | IXANY);

	options.c_lflag &= ~(ICANON | ECHO | ISIG);
	tcflush(fd, TCIFLUSH);
	tcsetattr(fd, TCSANOW, &options);
	
	return fd;
}

void alignDataStream(int fd) {
	char sentence[sentenceSize];
	
	do {
		read(fd, &sentence, 1);
	} while (sentence[0] != '\n');
}

float getEField(int fd) {
	int i;
	char sentence[sentenceSize];
	unsigned int oCheckSum, cCheckSum, status;
	float field;
	
	do {
		read(fd, &sentence, sizeof(sentence));
		usleep(100000);
	} while (sentence[0] != '$');
	
	cCheckSum = 0;
	for(i=0; i<10; i++) {
		cCheckSum += (unsigned int) sentence[i];
		cCheckSum %= 256;
	}
	sscanf(sentence, "$%6f,%i*%2X", &field, &status, &oCheckSum);
	if( oCheckSum == cCheckSum && status == 0 ) {
		return field;
	} else {
		return -9999.9;
	}
}

int main() {
	int i, fd;
	float efield, avgField, oldField;
	
	time_t t;
	
	t = time(NULL);
	printf("Started at %s", asctime(localtime(&t)));
	
	fd = readyPort("/dev/ttyUSB0");
	printf("Port ready\n");
	alignDataStream(fd);
	printf("Data aligned\n");
	
	oldField = 0.0;
	while(1) {
		i = 0;
		do {
			avgField +=  getEField(fd);
			t = time(NULL);
			i += 1;
		} while(i < 10);
		if( i == 10 ) {
			printf("At %li, E-field: %.4f kV/m\n", (long int) t, avgField/i);
			printf("-> Delta field: %.4f kV/m\n", avgField/i - oldField);
			oldField = avgField/i;
			avgField = 0.0;
			i = 0;
		}
	}
	
	
	close(fd);
	return(0);
}

