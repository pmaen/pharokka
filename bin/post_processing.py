from cmath import nan
import os
from re import T
import subprocess as sp
from Bio import SeqIO
import random
import string
from Bio.SeqUtils import GC
import pandas as pd
import numpy as np
pd.options.mode.chained_assignment = None

def process_results(db_dir,out_dir, prefix, gene_predictor):

    ##mmseqs

    mmseqs_file =  os.path.join(out_dir, "mmseqs_results.tsv")
    print("Processing mmseqs2 output.")
    col_list = ["phrog", "gene", "alnScore", "seqIdentity", "eVal", "qStart", "qEnd", "qLen", "tStart", "tEnd", "tLen"] 
    mmseqs_df = pd.read_csv(mmseqs_file, delimiter= '\t', index_col=False , names=col_list) 
    genes = mmseqs_df.gene.unique()

    tophits = []

    for gene in genes:
        tmp_df = mmseqs_df.loc[mmseqs_df['gene'] == gene].sort_values('eVal').reset_index(drop=True).loc[0]
        tophits.append([tmp_df.phrog, tmp_df.gene, tmp_df.alnScore, tmp_df.seqIdentity, tmp_df.eVal])

    tophits_df = pd.DataFrame(tophits, columns=['phrog', 'gene', 'alnScore', 'seqIdentity', 'eVal'])
    tophits_df.to_csv(os.path.join(out_dir, "top_hits_mmseqs.tsv"), sep="\t", index=False)
    # left join mmseqs top hits to phanotate
    phan_file = os.path.join(out_dir, "cleaned_" +  gene_predictor +  ".tsv") 
    # automatically picks up the names
    phan_df = pd.read_csv(phan_file, sep="\t", index_col=False )
    phan_df['gene']=phan_df['gene'].astype(str)
    tophits_df['gene']=tophits_df['gene'].astype(str)
    # merge top hit
    phan_df = phan_df[phan_df['start'].notna()]
    phan_df = phan_df.dropna()
    merged_df = phan_df.merge(tophits_df, on='gene', how='left')
    merged_df[['phrog','top_hit']] = merged_df['phrog'].str.split(' ## ',expand=True)
    merged_df["phrog"] = merged_df["phrog"].str.replace("phrog_", "")
    
    # get phrog annotaion file
    phrog_annot_df = pd.read_csv( os.path.join(db_dir, "phrog_annot_v4.tsv"), sep="\t", index_col=False )
    # merge phrog
    phrog_annot_df['phrog']=phrog_annot_df['phrog'].astype(str)
    merged_df = merged_df.merge(phrog_annot_df, on='phrog', how='left')
    merged_df = merged_df.replace(np.nan, 'No_PHROG', regex=True)
    merged_df['annot'] = merged_df["annot"].str.replace("No_PHROG", "hypothetical protein")
    merged_df['category'] = merged_df["category"].str.replace("No_PHROG", "unknown function")

    # add columns
    if gene_predictor == "phanotate":
        merged_df['Method'] = "PHANOTATE"
    if gene_predictor == "prodigal":
        merged_df['Method'] = "PRODIGAL"
    merged_df['Region'] = "CDS"

    # # replace with NA if nothing found for mmseqs
    merged_df.loc[merged_df['phrog'] == 'No_PHROG', 'phrog'] = 'No_PHROG'
    merged_df.loc[merged_df['alnScore'] == 'No_PHROG', 'alnScore'] = 'No_PHROG'
    merged_df.loc[merged_df['seqIdentity'] == 'No_PHROG', 'seqIdentity'] = 'No_PHROG'
    merged_df.loc[merged_df['eVal'] == 'No_PHROG', 'eVal'] = 'No_PHROG'
    merged_df.loc[merged_df['top_hit'] == 'No_PHROG', 'top_hit'] = 'No_PHROG'
    merged_df.loc[merged_df['color'] == 'No_PHROG', 'color'] = 'No_PHROG'
    
    # get phrog
    merged_df["phrog"] = merged_df["phrog"].str.replace("phrog_", "")
    merged_df['phrog']=merged_df['phrog'].astype(str)
    # drop existing color annot category cols
    merged_df = merged_df.drop(columns = ['color', 'annot', 'category'])
    merged_df = merged_df.merge(phrog_annot_df, on='phrog', how='left')
    merged_df["annot"] = merged_df["annot"].replace(nan, 'hypothetical protein', regex=True)
    merged_df["category"] = merged_df["category"].replace(nan, 'unknown function', regex=True)
    merged_df["color"] = merged_df["color"].replace(nan, 'none', regex=True)

    merged_df.to_csv( os.path.join(out_dir, prefix + "_final_merged_output.tsv"), sep="\t", index=False)
    
    return merged_df

def get_contig_name_lengths(fasta_input, out_dir, prefix):
    fasta_sequences = SeqIO.parse(open(fasta_input),'fasta')
    contig_names = []
    lengths = []
    gc = []
    for fasta in fasta_sequences:
        contig_names.append(fasta.id)
        lengths.append(len(fasta.seq))
        gc.append(round(GC(fasta.seq),2))
    length_df = pd.DataFrame(
    {'contig': contig_names,
     'length': lengths,
     'gc_perc': gc,
    })
    return(length_df)

def create_txt(phanotate_mmseqs_df, length_df, out_dir, prefix):

    contigs = length_df["contig"]
    # instantiate the length_df['cds_coding_density']
    length_df['cds_coding_density'] = 0.0
    description_list = []

    # read in trnascan

    col_list = ["contig", "Method", "Region", "start", "stop", "score", "frame", "phase", "attributes"]
    trna_df = pd.read_csv(os.path.join(out_dir,"trnascan_out.gff"), delimiter= '\t', index_col=False, names=col_list ) 
    # keep only trnas
    trna_df = trna_df[(trna_df['Region'] == 'tRNA') | (trna_df['Region'] == 'pseudogene')]

    # read in minced
    minced_df = pd.read_csv(os.path.join(out_dir, prefix + "_minced.gff"), delimiter= '\t', index_col=False, names=col_list, skiprows = 1  ) 

    for contig in contigs:
        phanotate_mmseqs_df_cont = phanotate_mmseqs_df[phanotate_mmseqs_df['contig'] == contig]
        cds_count = len(phanotate_mmseqs_df_cont[phanotate_mmseqs_df_cont['Region'] == 'CDS'])
        trna_count = len(trna_df['Region'])
        crispr_count = len(minced_df['Region'])
        # get the total length of the contig
        contig_length = length_df[length_df["contig"] == contig]['length']
        if cds_count > 0:
            # gets the total cds coding length
            cds_lengths = abs(phanotate_mmseqs_df_cont['start'] - phanotate_mmseqs_df_cont['stop']).sum()
            # get function
            phanotate_mmseqs_df_cont[['attributes2']] = phanotate_mmseqs_df_cont[['attributes']]
            phanotate_mmseqs_df_cont[['attributes2','function']] = phanotate_mmseqs_df_cont['attributes2'].str.split(';function=',expand=True)
            phanotate_mmseqs_df_cont = phanotate_mmseqs_df_cont.drop(columns=['attributes2'])
            phanotate_mmseqs_df_cont[['function','product']] = phanotate_mmseqs_df_cont['function'].str.split(';product=',expand=True)
            phanotate_mmseqs_df_cont = phanotate_mmseqs_df_cont.drop(columns=['product'])
            # get counts of functions and cds 
            regions = phanotate_mmseqs_df_cont['Region'].value_counts()
            functions = phanotate_mmseqs_df_cont['function'].value_counts()
            # reset index gets the names, then drop drops the first row (a blank index)
            description_df = pd.concat([regions, functions]).to_frame(name = "Test").reset_index()
            description_df.columns = ['Description', 'Count']
            description_df['contig'] = contig
        else:
            description_df = pd.DataFrame({'Description': ["CDS"], 'Count': [0], 'contig': contig})
            cds_lengths = 0
        # add trna count
        trna_row = pd.DataFrame({ 'Description':['tRNAs'], 'Count':[trna_count], 'contig':[contig] })
        crispr_row = pd.DataFrame({ 'Description':['CRISPRs'], 'Count':[crispr_count], 'contig':[contig] })
        # calculate the cds coding density and add to length_df
        cds_coding_density = cds_lengths * 100 / contig_length
        cds_coding_density = round(cds_coding_density, 2)
        length_df.loc[length_df['contig'] == contig, 'cds_coding_density'] = cds_coding_density
        # append it all
        description_list.append(description_df)
        description_list.append(trna_row)
        description_list.append(crispr_row)

    # save the output
    description_total_df = pd.concat(description_list)
    #description_total_df = description_total_df.append({'Description':'tRNAs', 'Count':trna_count, 'contig':contig}, ignore_index=True)
    description_total_df.to_csv(os.path.join(out_dir, prefix + "_cds_functions.tsv"), sep="\t", index=False)
    # save the length_gc.tsv also
    length_df.to_csv(os.path.join(out_dir, prefix + "_length_gc.tsv"), sep="\t", index=False)


  
def create_gff(phanotate_mmseqs_df, length_df, fasta_input, out_dir, prefix, locustag):
    # write the headers of the gff file
    with open(os.path.join(out_dir, prefix + ".gff"), 'w') as f:
        f.write('##gff-version 3\n')
        for index, row in length_df.iterrows():
            f.write('##sequence-region ' + row['contig'] + ' 1 ' + str(row['length']) +'\n')
  
    # rearrange start and stop so that start is always less than stop for gff
    cols = ["start","stop"]
    #indices where start is greater than stop
    ixs = phanotate_mmseqs_df['frame'] == '-'
    # Where ixs is True, values are swapped
    phanotate_mmseqs_df.loc[ixs,cols] = phanotate_mmseqs_df.loc[ixs, cols].reindex(columns=cols[::-1]).values

    if locustag == "Random":
        # locus tag header 8 random letters
        locustag = ''.join(random.choice(string.ascii_uppercase) for _ in range(8))
        
    
    phanotate_mmseqs_df['phase'] = 0
    phanotate_mmseqs_df['attributes'] = "ID=" + locustag + "_" + phanotate_mmseqs_df.index.astype(str)  + ";" + "phrog=" + phanotate_mmseqs_df["phrog"] + ";" + "top_hit=" + phanotate_mmseqs_df["top_hit"] + ";" + "locus_tag=" + locustag + "_" + phanotate_mmseqs_df.index.astype(str) + ";" + "function=" + phanotate_mmseqs_df["category"] + ";"  + "product=" + phanotate_mmseqs_df["annot"]

    # get gff dataframe in correct order 
    gff_df = phanotate_mmseqs_df[["contig", "Method", "Region", "start", "stop", "score", "frame", "phase", "attributes"]]

    # change start and stop to int 
    gff_df["start"] = gff_df["start"].astype('int')
    gff_df["stop"] = gff_df["stop"].astype('int')

    with open(os.path.join(out_dir, prefix + ".gff"), 'a') as f:
        gff_df.to_csv(f, sep="\t", index=False, header=False)
      
    ### trnas
    col_list = ["contig", "Method", "Region", "start", "stop", "score", "frame", "phase", "attributes"]
    trna_df = pd.read_csv(os.path.join(out_dir,"trnascan_out.gff"), delimiter= '\t', index_col=False, names=col_list ) 
    # keep only trnas
    trna_df = trna_df[(trna_df['Region'] == 'tRNA') | (trna_df['Region'] == 'pseudogene')]
    trna_df.start = trna_df.start.astype(int)
    trna_df.stop = trna_df.stop.astype(int)
    with open(os.path.join(out_dir, prefix + ".gff"), 'a') as f:
        trna_df.to_csv(f, sep="\t", index=False, header=False)

    ### crisprs
    minced_df = pd.read_csv(os.path.join(out_dir, prefix + "_minced.gff"), delimiter= '\t', index_col=False, names=col_list, skiprows = 1  ) 
    minced_df.start = minced_df.start.astype(int)
    minced_df.stop = minced_df.stop.astype(int)
    with open(os.path.join(out_dir, prefix + ".gff"), 'a') as f:
        minced_df.to_csv(f, sep="\t", index=False, header=False)

    # write fasta on the end 

    ##FASTA
    with open(os.path.join(out_dir, prefix + ".gff"), 'a') as f:
        f.write('##FASTA\n')
        fasta_sequences = SeqIO.parse(open(fasta_input),'fasta')
        SeqIO.write(fasta_sequences, f, "fasta")

def create_tbl(phanotate_mmseqs_df, length_df, out_dir, prefix, gene_predictor):

    ### readtrnas

    col_list = ["contig", "Method", "Region", "start", "stop", "score", "frame", "phase", "attributes"]

     # check if no trnas
    trna_empty = False
    if os.stat(os.path.join(out_dir, "trnascan_out.gff")).st_size == 0:
        trna_empty = True
    if trna_empty == False:    
        trna_df = pd.read_csv(os.path.join(out_dir, "trnascan_out.gff"), delimiter= '\t', index_col=False, names=col_list ) 
        # keep only trnas and pseudogenes 
        trna_df = trna_df[(trna_df['Region'] == 'tRNA') | (trna_df['Region'] == 'pseudogene')]
        trna_df.start = trna_df.start.astype(int)
        trna_df.stop = trna_df.stop.astype(int)

        trna_df[['attributes','isotypes']] = trna_df['attributes'].str.split(';isotype=',expand=True)
        trna_df[['isotypes','anticodon']] = trna_df['isotypes'].str.split(';anticodon=',expand=True)
        trna_df[['anticodon','rest']] = trna_df['anticodon'].str.split(';gene_biotype',expand=True)
        trna_df['trna_product']='tRNA-'+trna_df['isotypes']+"("+trna_df['anticodon']+")"

    # check if no crisprs
    crispr_empty = False
    if os.stat(os.path.join(out_dir, prefix + "_minced.gff")).st_size == 0:
        crispr_empty = True
    if crispr_empty == False:    
        crispr_df = pd.read_csv(os.path.join(out_dir, prefix + "_minced.gff"), delimiter= '\t', index_col=False, names=col_list, skiprows = 1  ) 
        # keep only trnas and pseudogenes 
        crispr_df.start = crispr_df.start.astype(int)
        crispr_df.stop = crispr_df.stop.astype(int)
        crispr_df[['attributes','rpt_unit_seq']] = crispr_df['attributes'].str.split(';rpt_unit_seq=',expand=True)


    if gene_predictor == "phanotate":
        inf = "PHANOTATE"
    else:
        inf = "PRODIGAL"
    with open( os.path.join(out_dir, prefix + ".tbl"), 'w') as f:
        for index, row in length_df.iterrows():
            contig = row['contig']
            f.write('>' + contig + '\n')
            subset_df = phanotate_mmseqs_df[phanotate_mmseqs_df['contig'] == contig]
            for index, row in subset_df.iterrows():
                f.write(str(row['start']) + "\t" + str(row['stop']) + "\t" + row['Region'] + "\n")
                f.write(""+"\t"+""+"\t"+""+"\t"+"inference" + "\t"+ inf + "\n")
                f.write(""+"\t"+""+"\t"+""+"\t"+"inference" + "\t"+ "phrog=" + str(row['phrog']) + "\n")
                f.write(""+"\t"+""+"\t"+""+"\t"+"product" + "\t"+ str(row['annot']) + "\n")
                f.write(""+"\t"+""+"\t"+""+"\t"+"transl_table" + "\t"+ "11" + "\n")
            if trna_empty == False:
                subset_trna_df = trna_df[trna_df['contig'] == contig]
                for index, row in subset_trna_df.iterrows():
                    f.write(str(row['start']) + "\t" + str(row['stop']) + "\t" + row['Region'] + "\n")
                    f.write(""+"\t"+""+"\t"+""+"\t"+"inference" + "\t"+ "tRNAscan-SE")
                    f.write(""+"\t"+""+"\t"+""+"\t"+"product" + "\t"+ str(row['trna_product']) + "\n")
                    f.write(""+"\t"+""+"\t"+""+"\t"+"transl_table" + "\t"+ "11" + "\n")
            if crispr_empty == False:
                subset_crispr_df = crispr_df[crispr_df['contig'] == contig]
                for index, row in subset_crispr_df.iterrows():
                    f.write(str(row['start']) + "\t" + str(row['stop']) + "\t" + row['Region'] + "\n")
                    f.write(""+"\t"+""+"\t"+""+"\t"+"inference" + "\t"+ "MinCED")
                    f.write(""+"\t"+""+"\t"+""+"\t"+"product" + "\t"+ str(row['rpt_unit_seq']) + "\n")
                    f.write(""+"\t"+""+"\t"+""+"\t"+"transl_table" + "\t"+ "11" + "\n")

def remove_post_processing_files(out_dir, gene_predictor):
    sp.run(["rm", "-rf", os.path.join(out_dir, "target_dir") ])
    sp.run(["rm", "-rf", os.path.join(out_dir, "tmp_dir/") ])
    sp.run(["rm", "-rf", os.path.join(out_dir, "mmseqs/") ])
    sp.run(["rm", "-rf", os.path.join(out_dir, "cleaned_" + gene_predictor + ".tsv") ])
    sp.run(["rm", "-rf", os.path.join(out_dir, "input_fasta_delim.fasta") ])
    sp.run(["rm", "-rf", os.path.join(out_dir, "mmseqs_results.tsv") ])
    # leave in tophits
    sp.run(["rm", "-rf", os.path.join(out_dir, gene_predictor + "_aas_tmp.fasta") ])
    sp.run(["rm", "-rf", os.path.join(out_dir, gene_predictor + "_out_tmp.fasta") ])
    if gene_predictor == "phanotate":
        sp.run(["rm", "-rf", os.path.join(out_dir, "phanotate_out.txt") ])
    if gene_predictor == "prodigal":
        sp.run(["rm", "-rf", os.path.join(out_dir, "prodigal_out.gff") ])







