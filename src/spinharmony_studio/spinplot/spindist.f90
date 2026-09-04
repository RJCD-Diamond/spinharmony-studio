program correlation
implicit none

integer :: i,j,l,k,n,num_atoms,num_boxes,ibox,permute(3)
integer, parameter :: dp = kind(1.d0)
real(dp),allocatable :: atoms(:,:),spins(:,:,:),axis_old(:,:,:),axis(:,:,:)
real(dp),allocatable :: cell_coords(:,:),histogram(:,:,:),histogram_avg(:,:),histogram_err(:,:)
real(dp),parameter :: pi=acos(-1d0),eps=2d0*epsilon(0d0)
real(dp) :: norm,s_old(3),rot(3,3),s_new(3)
integer :: num_atoms_in_cell,atom_count,a,x,z,y,num_cells(3)
character(2) :: itc2
character(1) :: tchar
character(128) :: mult_spin_file,title,filename_stem,arg
character(1000) :: str
real(dp) :: cell_params(3),s(3),min,thetay,theta,phi,dphi,dtheta,mag(3)
logical :: file_exists
integer :: ntheta,nphi,itheta,iphi
integer,allocatable :: supercell(:,:)
real(dp) :: max,err,cross(3)
integer :: max_loc(2),min_loc(2)

write(*,*) 'Welcome to SPINDIST'
write(*,*) 'Spin orientation distribution function calculator'
write(*,*) 'written by Andrew L. Goodwin, Joe Paddison'
write(*,*) '(version dated 29 Oct 2014)'
write(*,*) ''

!Read input from the command line
i = iargc()
if (i<1) then
 write(*,*) 'Please start the program by writing ./spindist [input file name stem]'
 write(*,*) ''
 stop
else
 call getarg(1,filename_stem)
 call getarg(2,arg)
 read(arg,*) ntheta
 call getarg(3,arg)
 read(arg,*) nphi
endif
 
atom_count=0
num_boxes=0
do n=1,100
mult_spin_file=trim(adjustl(filename_stem))//'_spins_'//itc2(n)//'.txt'
inquire(file=mult_spin_file, exist=file_exists)
 if (file_exists.eqv..true.) then
  num_boxes=num_boxes+1 
  if (num_boxes==1) then
   call read_config1(mult_spin_file,title,cell_params,num_atoms_in_cell,num_cells)
   allocate(cell_coords(3,num_atoms_in_cell))
   cell_coords=0d0 
   call read_config2(mult_spin_file,cell_coords,num_atoms_in_cell)
  endif
 endif
enddo
if (num_boxes==0) then
 write(*,*) 'No spin configurations found'
 stop
endif
write(*,'(i3,a)') num_boxes,' spin configurations found'

allocate(axis(3,3,num_atoms_in_cell))
allocate(axis_old(3,3,num_atoms_in_cell))
axis_old=0d0
axis=0d0
permute(:)=[1,2,3]

j=0
k=0
l=0

open(11,file=trim(adjustl(filename_stem))//'_spindist_config.txt',status='old')
do
 read(11,'(a)',end=15) str
 i = index(str,'PERMUTE')
  if(i.ne.0) read(str(i+7:),*) permute(:)
enddo
15 rewind(11)
do
 read(11,'(a)',end=25) str
 i = index(str,'X')
 if(i.ne.0) then
  j=j+1
  read(str(i+1:),*)  axis_old(:,1,j)
 endif
 i = index(str,'Y')
 if(i.ne.0) then 
  k=k+1
  read(str(i+1:),*)  axis_old(:,2,k)
 endif
 i = index(str,'Z')
 if(i.ne.0) then
  l=l+1
  read(str(i+1:),*)  axis_old(:,3,l)
 endif
enddo
25 close(11)
do j=1,num_atoms_in_cell
 do i=1,3
  norm=sqrt(dot_product(axis_old(:,i,j),axis_old(:,i,j)))
  if (abs(norm)<eps) write(*,*) 'Error - X,Y,Z not specified'
  axis_old(:,i,j)=axis_old(:,i,j)/norm ! normalise
 enddo
enddo

write(*,*) permute

do i=1,3
 axis(:,i,:)=axis_old(:,permute(i),:)
enddo
 
write(*,*) 'Configuration file "',trim(adjustl(filename_stem))//'_spindist_config.txt', '" read successfully!'
write(*,*) ''

num_atoms=num_atoms_in_cell*num_cells(1)*num_cells(2)*num_cells(3)
allocate(spins(3,num_atoms,num_boxes))
allocate(atoms(3,num_atoms))

do j=1,num_atoms_in_cell
 do i=1,3
  norm=sqrt(dot_product(axis(:,i,j),axis(:,i,j)))
  axis(:,i,j)=axis(:,i,j)/norm
 enddo
   write(*,*) 'Site ',j
   write(*,*) 'X ',axis(:,1,j)
   write(*,*) 'Y ',axis(:,2,j)
   write(*,*) 'Z ',axis(:,3,j)
   call cross_product(axis(:,1,j),axis(:,2,j),cross)
   write(*,*) 'X x Y ', cross
   write(*,*) ''
enddo

do k=1,num_atoms_in_cell
do i=1,3
 do j=1,i-1
  if (abs(dot_product(axis(:,i,k),axis(:,j,k)))>10d0*eps) then
   write(*,*) 'Warning - axes do not seem to be orthogonal!'
  endif
 enddo
enddo
enddo

allocate(supercell(4,num_atoms))

ibox=0
do n=1,100
mult_spin_file=trim(adjustl(filename_stem))//'_spins_'//itc2(n)//'.txt'
inquire(file=mult_spin_file, exist=file_exists)   
if (file_exists.eqv..true.) then
ibox=ibox+1
open(11,file=mult_spin_file,status='old')
atom_count=0
do
   read(11,'(a)',end=12) str
   i = index(str,'SPIN')
   if(i.ne.0) then
    atom_count=atom_count+1 
    read(str(i+4:),*) a,x,y,z,spins(:,atom_count,ibox)
    supercell(:,atom_count)=[a,x,y,z]
 if(atom_count.gt.num_atoms) then
  write(*,*) 'Input error - incorrrect number of entries for SPIN in file',mult_spin_file
  stop
    atoms(:,atom_count)=cell_coords(:,a)+(/x,y,z/)
    atoms(:,atom_count)=atoms(:,atom_count)*cell_params(:)
   endif
  endif
 enddo
12 continue
close(11)
endif
num_atoms=atom_count
 if(atom_count.ne.num_atoms) then
  write(*,*) 'Input error - incorrrect number of entries for SPIN in file',mult_spin_file
  stop
 endif
 do i=1,num_atoms
  norm=sqrt(dot_product(spins(:,i,ibox),spins(:,i,ibox)))
  if (abs(norm-1d0)>eps) then
   write(*,*) 'Warning - spins do not seem to be normalised. Spins will be normalised to 1 before proceeding',i,norm
  endif
  spins(:,i,ibox)=spins(:,i,ibox)/norm  
 enddo
enddo

dphi=pi/nphi
write(*,*)'Value of dphi = ',dphi
dtheta=2d0*pi/ntheta
write(*,*)'Value of dtheta = ',dtheta

allocate(histogram(nphi,ntheta,num_boxes))
allocate(histogram_avg(nphi,ntheta))
allocate(histogram_err(nphi,ntheta))

histogram_avg=0d0
histogram_err=0d0
histogram=0d0

min=num_boxes*num_atoms

write(*,*) ''
do ibox=1,num_boxes
 do i=1,num_atoms
  s_old(:)=spins(:,i,ibox)
  a=supercell(1,i)

do j=1,3
 s(j)=dot_product(axis(:,j,a),s_old(:))
enddo

if(abs(dot_product(s,s)-1d0)>10d0*eps) then
 write(*,*) dot_product(s,s),a,i
 write(*,*) dot_product(spins(:,i,ibox),spins(:,i,ibox))
 do k=1,3
  write(*,*) axis(:,k,a)
 enddo
 stop 'Error - axes do not seem to be normalised'
endif

norm=sqrt(dot_product(s,s))
s=s/norm

 phi=acos(s(3))
 theta=atan2(s(2),s(1))
 if(theta<0d0) theta=2d0*pi+theta
 
 if(isnan(theta)) stop 'theta Nan'
 if(isnan(phi)) stop 'phi Nan'

 iphi=int(nphi*(1d0-cos(phi))/2d0)+1
 itheta=int(theta/dtheta)+1

 if(iphi>nphi) then
  write(*,*) 'Warning - iphi>nphi',iphi ! this can happen with Ising spins due to rounding
  iphi=nphi
 endif
 if(iphi<1) then
  write(*,*) 'Warning - iphi<1',iphi
  iphi=1
 endif
 if(itheta>ntheta) then
  write(*,*) 'Warning - itheta>ntheta' ,itheta
  itheta=ntheta
 endif
 if(itheta<1) then
  write(*,*) 'Warning - itheta<1' 
  itheta=1
 endif
 
 histogram(iphi,itheta,ibox)=histogram(iphi,itheta,ibox)+4d0*pi/(num_atoms*dtheta*dphi*2d0/pi)

 enddo
enddo

do iphi=1,nphi
 do itheta=1,ntheta
  histogram_avg(iphi,itheta)=sum(histogram(iphi,itheta,:))
 enddo
enddo
histogram_avg=histogram_avg/(1d0*num_boxes)

do iphi=1,nphi
 do itheta=1,ntheta
  histogram_err(iphi,itheta)=sum((histogram(iphi,itheta,:)-histogram_avg(iphi,itheta))**2d0)
 enddo
enddo
if(num_boxes>1) histogram_err=sqrt(histogram_err/(1d0*num_boxes*(num_boxes-1)))

min=huge(0d0)
max=-huge(0d0)

do iphi=1,nphi 
 do itheta=1,ntheta
   if(histogram_avg(iphi,itheta)<min) then
    min=histogram_avg(iphi,itheta)
    min_loc(:)=[iphi,itheta]
   endif
   if(histogram_avg(iphi,itheta)>max) then
    max=histogram_avg(iphi,itheta)
    max_loc(:)=[iphi,itheta]
   endif   
 enddo
enddo

if(abs(min)<eps) then 
 write(*,*) 'Minimum value in histogram is zero - looking for smallest non-zero value for log plot'
min=huge(0d0)
do iphi=1,nphi 
 do itheta=1,ntheta
   if((histogram_avg(iphi,itheta)<min).and.(abs(histogram_avg(iphi,itheta))>eps)) then
    min=histogram_avg(iphi,itheta)
    min_loc(:)=[iphi,itheta]
   endif
 enddo
enddo 
endif

write(*,*) 'max ',log(maxval(histogram_avg)),histogram_err(max_loc(1),max_loc(2))/maxval(histogram_avg)
write(*,*) 'min >0 ',log(min),histogram_err(min_loc(1),min_loc(2))/abs(min)


do iphi=1,nphi
 do itheta=1,ntheta
  if (histogram_avg(iphi,itheta)>0d0) then
   histogram_avg(iphi,itheta)=log(histogram_avg(iphi,itheta))
  else
   histogram_avg(iphi,itheta)=log(min)
  endif
 enddo
enddo           

open(12,file=trim(adjustl(filename_stem))//'_spindist.txt',status='replace')
write(12,*)ntheta,nphi
 do iphi=1,nphi
  write(12,'(F11.6,400(2X,F11.6))') histogram_avg(iphi,:)
 enddo
close(12)

write(*,*) 'Spin orientation distribution function written to file ',trim(adjustl(filename_stem))//'_spindist.txt'

end program correlation


subroutine cross_product(a,b,c)                         

implicit none    
integer, parameter :: dp = kind(1.d0)  
real(dp),intent(in) :: a(3)                   
real(dp),intent(in) :: b(3)                        
real(dp),intent(out) :: c(3)                   

c(1) = a(2)*b(3) - a(3)*b(2)                                           
c(2) = a(3)*b(1) - a(1)*b(3)
c(3) = a(1)*b(2) - a(2)*b(1)

end subroutine cross_product 


subroutine read_config1(mult_spin_file,title,cell_params,num_atoms_in_cell,num_cells)
implicit none

integer, parameter :: dp = kind(1.d0)
character(48),intent(in) :: mult_spin_file
integer,intent(out) :: num_atoms_in_cell,num_cells(3)
real(dp),intent(out) :: cell_params(3)
real(dp),parameter :: eps=2d0*epsilon(0d0)
character(48),intent(out) :: title
character(200) :: str
integer :: i,j

num_atoms_in_cell=0
num_cells=0
cell_params=0d0

open(11,file=mult_spin_file,status='old')
do
   read(11,'(a)',end=22) str
   i = index(str,'TITLE')
   if(i.ne.0) read(str(i+5:),*) title
   i = index(str,'CELL')
   if(i.ne.0) read(str(i+4:),*) (cell_params(j),j=1,3)
   i = index(str,'BOX')
   if(i.ne.0) read(str(i+3:),*) (num_cells(j),j=1,3)
enddo
22 rewind (11)
do
   read(11,'(a)',end=23) str
   i = index(str,'SITE')
   if(i.ne.0) num_atoms_in_cell=num_atoms_in_cell+1
enddo
23 close(11)

if (abs(sum(cell_params))<eps) then
 write(*,*) 'Input error - please specify CELL in spin file'
 stop
endif
if (sum(num_cells)==0) then
 write(*,*) 'Input error - please specify BOX in spin file'
 stop
endif

end subroutine read_config1

subroutine read_config2(mult_spin_file,atoms,num_atoms_in_cell)
implicit none

integer, parameter :: dp = kind(1.d0)
integer,intent(in) :: num_atoms_in_cell
character(48),intent(in) :: mult_spin_file
real(dp),intent(inout) :: atoms(3,num_atoms_in_cell)
real(dp),parameter :: eps=2d0*epsilon(0d0)
integer :: count,j,i
character(200) :: str

atoms=0d0
open(11,file=mult_spin_file,status='old')
count=0
do
   read(11,'(a)',end=10) str
   i = index(str,'SITE')
   if(i.ne.0) then
    count=count+1
 if(count>num_atoms_in_cell) then
  write(*,*) 'Input error. Please check number of SITE in config.txt 1'
  stop
 endif
 read(str(i+4:),*)  (atoms(j,count),j=1,3)
   endif
enddo
10 continue
close(11)
if (count<num_atoms_in_cell) then
 write(*,*) 'Input error. Please check number of SITE in config.txt 2',count,num_atoms_in_cell
 stop
endif
end subroutine read_config2


function  itc2(i)
character(2)  itc2
integer  i,i0,i1,i2 
itc2=''
i0=mod(i,100)
i1=i0/10
if(i1.eq.0)itc2='0'
if(i1.eq.1)itc2='1'
if(i1.eq.2)itc2='2'
if(i1.eq.3)itc2='3'
if(i1.eq.4)itc2='4'
if(i1.eq.5)itc2='5'
if(i1.eq.6)itc2='6'
if(i1.eq.7)itc2='7'
if(i1.eq.8)itc2='8'
if(i1.eq.9)itc2='9'
i2=i0
i2=i2-(10*i1)
if(i2.eq.0)itc2=itc2(1:1)//'0'
if(i2.eq.1)itc2=itc2(1:1)//'1'
if(i2.eq.2)itc2=itc2(1:1)//'2'
if(i2.eq.3)itc2=itc2(1:1)//'3'
if(i2.eq.4)itc2=itc2(1:1)//'4'
if(i2.eq.5)itc2=itc2(1:1)//'5'
if(i2.eq.6)itc2=itc2(1:1)//'6'
if(i2.eq.7)itc2=itc2(1:1)//'7'
if(i2.eq.8)itc2=itc2(1:1)//'8'
if(i2.eq.9)itc2=itc2(1:1)//'9'
end
